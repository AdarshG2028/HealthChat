"""Conversation orchestrator (§34), with the agreed API-call budget.

Gathering turn:  1 LLM call (extract + red flags + sufficiency + next question).
Decision turn:   1 LLM call (extract) -> 1 Jev call -> 1 LLM call (explanation, template fallback).
Emergencies skip the explanation call entirely (deterministic, fastest, safest).
Everything is recorded as WorkflowEvents so the Decision Trace needs zero extra calls.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from opentelemetry.trace import Status, StatusCode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.db.models import Conversation, JevDecisionRow, Message, PatientStateRow, WorkflowEvent
from app.domain.enums import MessageRole, MissingInfo, WorkflowAction
from app.domain.enums import WorkflowEventType as E
from app.domain.enums import WorkflowState as S
from app.domain.patient_state import DECISION_RELEVANT_FIELDS, PatientState, PatientStateUpdate
from app.domain.state_machine import transition
from app.jev.types import JevCaseInput, JevDecision, JevDecisionProvider, JevUnavailableError
from app.llm import templates
from app.llm.types import (
    ChatTurn,
    ExplanationContext,
    LLMProvider,
    LLMRateLimitedError,
    LLMUnavailableError,
    TurnContext,
)
from app.observability.logging import log
from app.observability.telemetry import tracer
from app.safety.policy import FinalDecision, PolicyConfig, apply_policy
from app.safety.red_flags import detect_red_flags
from app.services import limits
from app.services.errors import (
    ConversationClosedError,
    ConversationNotFoundError,
    InvalidOperationError,
    UpstreamUnavailableError,
)

RECENT_MESSAGES_FOR_LLM = 4
DAILY_QUOTA_RETRY_AFTER_SECONDS = 120


@dataclass
class TurnResult:
    conversation: Conversation
    assistant_message: Message
    state: PatientState
    decision: JevDecisionRow | None
    replayed: bool = False


class ConversationService:
    def __init__(
        self,
        session: AsyncSession,
        llm: LLMProvider,
        jev: JevDecisionProvider,
        settings: Settings,
        request_id: str | None = None,
    ) -> None:
        self.session = session
        self.llm = llm
        self.jev = jev
        self.settings = settings
        self.request_id = request_id
        self.policy_config = PolicyConfig(
            confidence_threshold=settings.confidence_escalation_threshold,
            human_review_threshold=settings.human_review_threshold,
            max_ask_more_rounds=settings.max_ask_more_rounds,
        )

    # ------------------------------------------------------------------ queries

    async def get(self, conversation_id: uuid.UUID, *, lock: bool = False) -> Conversation:
        stmt = (
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .options(selectinload(Conversation.messages), selectinload(Conversation.patient_state))
        )
        if lock:
            stmt = stmt.with_for_update()
        conversation = await self.session.scalar(stmt)
        if conversation is None:
            raise ConversationNotFoundError()
        return conversation

    async def decisions(self, conversation_id: uuid.UUID) -> list[JevDecisionRow]:
        result = await self.session.scalars(
            select(JevDecisionRow)
            .where(JevDecisionRow.conversation_id == conversation_id)
            .order_by(JevDecisionRow.created_at)
        )
        return list(result)

    async def latest_decision(self, conversation_id: uuid.UUID) -> JevDecisionRow | None:
        decisions = await self.decisions(conversation_id)
        return decisions[-1] if decisions else None

    async def events(self, conversation_id: uuid.UUID) -> list[WorkflowEvent]:
        result = await self.session.scalars(
            select(WorkflowEvent).where(WorkflowEvent.conversation_id == conversation_id).order_by(WorkflowEvent.id)
        )
        return list(result)

    @staticmethod
    def state_of(conversation: Conversation) -> PatientState:
        row = conversation.patient_state
        return PatientState.model_validate(row.state) if row else PatientState()

    # ------------------------------------------------------------------ commands

    async def start(self, client_ip: str | None = None, *, reset_from: uuid.UUID | None = None) -> TurnResult:
        ip_hash = limits.hash_ip(client_ip, self.settings.ip_hash_salt.get_secret_value())
        await limits.check_start_limits(self.session, self.settings, ip_hash)
        conversation = Conversation(
            status=S.COLLECTING_INFORMATION,
            llm_provider=self.llm.name,
            jev_provider=self.jev.name,
            client_ip_hash=ip_hash,
            messages=[],
        )
        state = PatientState()
        conversation.patient_state = PatientStateRow(state=state.model_dump(mode="json"))
        self.session.add(conversation)
        await self.session.flush()
        self._event(conversation, E.CONVERSATION_STARTED, reset_from=str(reset_from) if reset_from else None)
        greeting = self._add_message(conversation, MessageRole.ASSISTANT, templates.GREETING)
        await self.session.flush()
        return TurnResult(conversation, greeting, state, None)

    async def handle_message(
        self, conversation_id: uuid.UUID, content: str, idempotency_key: str | None = None
    ) -> TurnResult:
        with tracer.start_as_current_span("conversation.request") as span:
            span.set_attribute("conversation.id", str(conversation_id))
            if self.request_id:
                span.set_attribute("request.id", self.request_id)

            conversation = await self.get(conversation_id, lock=True)

            if idempotency_key and (replay := await self._replay(conversation, idempotency_key)):
                span.set_attribute("idempotent.replay", True)
                return replay

            status = S(conversation.status)
            if status != S.COLLECTING_INFORMATION:
                raise ConversationClosedError(status)

            state = self.state_of(conversation)
            recent = [
                ChatTurn.model_validate({"role": m.role, "content": m.content})
                for m in conversation.messages[-RECENT_MESSAGES_FOR_LLM:]
            ]
            turn = conversation.turn_count + 1
            rule_flags = detect_red_flags(content)

            # ---- 1 LLM call: extraction + red flags + sufficiency + next question
            extraction = None
            llm_failure: LLMUnavailableError | None = None
            with tracer.start_as_current_span("llm.extract") as llm_span:
                llm_span.set_attribute("llm.provider", self.llm.name)
                llm_span.set_attribute("llm.model", self.llm.model)
                try:
                    extraction = await self.llm.extract_turn(
                        TurnContext(
                            patient_state=state,
                            recent_messages=recent,
                            user_message=content,
                            turn=turn,
                            max_turns=self.settings.max_turns,
                        )
                    )
                    llm_span.set_attribute("llm.latency_ms", extraction.meta.latency_ms)
                except LLMUnavailableError as exc:
                    llm_span.set_status(Status(StatusCode.ERROR))
                    llm_span.set_attribute("error.type", exc.reason)
                    if not rule_flags:
                        # Nothing safety-critical: roll the turn back so the client can retry cleanly.
                        await self._record_llm_failure(conversation_id, exc)
                        raise self._upstream_error(exc) from exc
                    # Emergency detected by deterministic rules: continue without the LLM.
                    llm_failure = exc

            user_message = self._add_message(conversation, MessageRole.USER, content, idempotency_key)
            conversation.turn_count = turn
            self._event(conversation, E.MESSAGE_RECEIVED, turn=turn, length=len(content))
            if llm_failure:
                self._event(conversation, E.LLM_FAILED, reason=llm_failure.reason, continued="red_flag_rules")

            # ---- state update
            with tracer.start_as_current_span("state.update"):
                changed: list[str] = []
                llm_flags = []
                if extraction:
                    self._event(
                        conversation,
                        E.LLM_EXTRACTION,
                        provider=extraction.meta.provider,
                        model=extraction.meta.model,
                        latency_ms=extraction.meta.latency_ms,
                        input_tokens=extraction.meta.input_tokens,
                    )
                    state, changed = state.merge(extraction.to_update())
                    llm_flags = extraction.output.red_flags
                state, new_flags = state.add_red_flags([*rule_flags, *llm_flags])
                self._save_state(conversation, state)
                self._event(conversation, E.PATIENT_STATE_UPDATED, fields=changed)
                if new_flags:
                    self._event(
                        conversation,
                        E.RED_FLAG_DETECTED,
                        flags=[str(f) for f in new_flags],
                        sources=_flag_sources(new_flags, rule_flags, llm_flags),
                    )

            # ---- enough information?
            turn_cap = turn >= self.settings.max_turns
            if turn_cap:
                self._event(conversation, E.TURN_CAP_REACHED, turn=turn)
            llm_sufficient = bool(extraction and extraction.output.info_sufficient)
            ready_reason = (
                "red_flag"
                if state.red_flags
                else "turn_cap"
                if turn_cap
                else "sufficient"
                if llm_sufficient and state.has_minimum_core()
                else None
            )

            decision_row = None
            if ready_reason is None:
                reply = self._next_question(state, extraction.output.next_question if extraction else None)
                self._transition(conversation, S.COLLECTING_INFORMATION)
                self._event(conversation, E.INFORMATION_COLLECTION_CONTINUED, source="llm")
                assistant = self._add_message(conversation, MessageRole.ASSISTANT, reply, reply_to=user_message.id)
            else:
                self._transition(conversation, S.READY_FOR_DECISION)
                assistant, decision_row = await self._decide(
                    conversation, state, ready_reason, reply_to=user_message.id
                )

            span.set_attribute("workflow.state", conversation.status)
            await self.session.flush()
            return TurnResult(conversation, assistant, state, decision_row)

    async def correct_state(self, conversation_id: uuid.UUID, corrections: PatientStateUpdate) -> TurnResult | None:
        """Apply user corrections. Re-evaluates at most `max_reevaluations` times after a decision."""
        with tracer.start_as_current_span("conversation.correct") as span:
            span.set_attribute("conversation.id", str(conversation_id))
            conversation = await self.get(conversation_id, lock=True)
            state, changed = self.state_of(conversation).correct(corrections)
            state, new_flags = state.add_red_flags(detect_red_flags(*state.text_values()))
            self._save_state(conversation, state)
            self._event(conversation, E.PATIENT_STATE_CORRECTED, fields=changed)
            if new_flags:
                self._event(conversation, E.RED_FLAG_DETECTED, flags=[str(f) for f in new_flags], sources=["rules"])

            status = S(conversation.status)
            relevant = bool(set(changed) & DECISION_RELEVANT_FIELDS) or bool(new_flags)
            if status in {S.COMPLETED, S.ESCALATED} and relevant:
                if conversation.reevaluations >= self.settings.max_reevaluations:
                    raise InvalidOperationError("This recommendation has already been updated once.")
                conversation.reevaluations += 1
                self._transition(conversation, S.READY_FOR_DECISION)
                assistant, row = await self._decide(conversation, state, "correction")
                await self.session.flush()
                return TurnResult(conversation, assistant, state, row)
            await self.session.flush()
            return None

    async def retry_decision(self, conversation_id: uuid.UUID) -> TurnResult:
        conversation = await self.get(conversation_id, lock=True)
        if S(conversation.status) != S.ERROR:
            raise InvalidOperationError("Only a failed decision can be retried.")
        if conversation.reevaluations >= self.settings.max_reevaluations:
            raise InvalidOperationError("The decision has already been retried.")
        conversation.reevaluations += 1
        state = self.state_of(conversation)
        self._transition(conversation, S.READY_FOR_DECISION)
        assistant, row = await self._decide(conversation, state, "retry")
        await self.session.flush()
        return TurnResult(conversation, assistant, state, row)

    # ------------------------------------------------------------------ decision

    async def _decide(
        self, conversation: Conversation, state: PatientState, reason: str, reply_to: uuid.UUID | None = None
    ) -> tuple[Message, JevDecisionRow | None]:
        self._event(conversation, E.READY_FOR_JEV, reason=reason)
        self._transition(conversation, S.JEV_PROCESSING)

        # ---- exactly ONE Jev call
        with tracer.start_as_current_span("jev.evaluate") as jev_span:
            jev_span.set_attribute("jev.provider", self.jev.name)
            try:
                if await limits.jev_daily_cap_reached(self.session, self.settings):
                    raise JevUnavailableError("daily_cap", retryable=False)
                decision = await self.jev.evaluate_case(
                    JevCaseInput(
                        patient_state=state,
                        red_flags=state.red_flags,
                        turn_count=conversation.turn_count,
                        ask_more_rounds_used=conversation.ask_more_rounds,
                    )
                )
            except JevUnavailableError as exc:
                jev_span.set_status(Status(StatusCode.ERROR))
                jev_span.set_attribute("error.type", exc.reason)
                log.warning(
                    "jev.decision.failed",
                    conversation_id=str(conversation.id),
                    request_id=self.request_id,
                    reason=exc.reason,
                )
                self._event(conversation, E.JEV_FAILED, reason=exc.reason, retryable=exc.retryable)
                self._transition(conversation, S.ERROR)
                text = templates.decision_unavailable(emergency=bool(state.red_flags))
                return self._add_message(conversation, MessageRole.ASSISTANT, text, reply_to=reply_to), None

            jev_span.set_attribute("jev.model", decision.model)
            jev_span.set_attribute("jev.latency_ms", decision.latency_ms)
            jev_span.set_attribute("jev.action", decision.action)
            jev_span.set_attribute("jev.department", decision.department)
            jev_span.set_attribute("jev.urgency", decision.urgency)
            jev_span.set_attribute("jev.complexity", decision.complexity)

        self._event(
            conversation,
            E.JEV_DECISION_COMPLETED,
            action=decision.action,
            department=decision.department,
            urgency=decision.urgency,
            complexity=decision.complexity,
            human_review_probability=decision.human_review_probability,
            action_confidence=decision.action_confidence,
            model=decision.model,
            latency_ms=decision.latency_ms,
        )
        log.info(
            "jev.decision.completed",
            conversation_id=str(conversation.id),
            request_id=self.request_id,
            action=decision.action,
            department=decision.department,
            urgency=decision.urgency,
            complexity=decision.complexity,
        )

        # ---- deterministic policy + execution
        with tracer.start_as_current_span("workflow.execute") as wf_span:
            final = apply_policy(
                decision,
                red_flags=state.red_flags,
                ask_more_rounds_used=conversation.ask_more_rounds,
                turn_cap_reached=conversation.turn_count >= self.settings.max_turns,
                config=self.policy_config,
            )
            for o in final.overrides:
                self._event(conversation, E.POLICY_OVERRIDE, rule=o.rule, field=o.field, before=o.before, after=o.after)
            row = self._save_decision(conversation, decision, final)
            self._transition(conversation, S.EXECUTING_ACTION)
            self._event(
                conversation, E.ACTION_EXECUTED, action=final.action, department=final.department, urgency=final.urgency
            )
            wf_span.set_attribute("workflow.action", final.action)

            if final.action == WorkflowAction.ASK_MORE_INFORMATION:
                conversation.ask_more_rounds += 1
                self._transition(conversation, S.COLLECTING_INFORMATION)
                self._event(
                    conversation, E.INFORMATION_COLLECTION_CONTINUED, source="jev", missing_info=decision.missing_info
                )
                text = templates.ask_more_question(decision.missing_info)
                return self._add_message(conversation, MessageRole.ASSISTANT, text, reply_to=reply_to), row

            if final.human_review_recommended or final.action == WorkflowAction.ESCALATE_TO_HUMAN:
                self._event(conversation, E.HUMAN_REVIEW_REQUIRED, probability=decision.human_review_probability)

        text = await self._explain(conversation, state, final)
        self._transition(conversation, final.next_state)
        self._event(conversation, E.CONVERSATION_COMPLETED, status=conversation.status)
        return self._add_message(conversation, MessageRole.ASSISTANT, text, reply_to=reply_to), row

    async def _explain(self, conversation: Conversation, state: PatientState, final: FinalDecision) -> str:
        if final.emergency:
            # No LLM call for emergencies: deterministic wording, zero latency, zero cost.
            text = templates.explanation(final.action, final.department, final.urgency, state)
            self._event(conversation, E.EXPLANATION_FALLBACK_USED, reason="emergency_template")
        else:
            with tracer.start_as_current_span("llm.response") as span:
                span.set_attribute("llm.provider", self.llm.name)
                try:
                    explanation = await self.llm.explain_decision(
                        ExplanationContext(
                            action=final.action,
                            department=final.department,
                            urgency=final.urgency,
                            complexity=final.complexity,
                            human_review_recommended=final.human_review_recommended,
                            emergency=final.emergency,
                            patient_state=state,
                        )
                    )
                    text = explanation.text
                    span.set_attribute("llm.latency_ms", explanation.meta.latency_ms)
                    self._event(
                        conversation,
                        E.LLM_RESPONSE_GENERATED,
                        provider=explanation.meta.provider,
                        latency_ms=explanation.meta.latency_ms,
                    )
                except LLMUnavailableError as exc:
                    span.set_attribute("error.type", exc.reason)
                    text = templates.explanation(final.action, final.department, final.urgency, state)
                    self._event(conversation, E.EXPLANATION_FALLBACK_USED, reason=exc.reason)
        if final.crisis_support:
            text = f"{templates.CRISIS_NOTICE} {text}"
        return text

    # ------------------------------------------------------------------ helpers

    def _next_question(self, state: PatientState, llm_question: str | None) -> str:
        if llm_question and llm_question.strip():
            return llm_question.strip()
        missing = state.missing_core_fields()
        return templates.core_question(missing[0]) if missing else templates.ask_more_question(MissingInfo.NONE)

    def _transition(self, conversation: Conversation, target: S) -> None:
        current = S(conversation.status)
        conversation.status = transition(current, target)
        if current != target:
            self._event(conversation, E.WORKFLOW_STATE_CHANGED, from_state=current, to_state=target)

    def _event(self, conversation: Conversation, event_type: E, **data: Any) -> None:
        clean = {k: (str(v) if hasattr(v, "value") else v) for k, v in data.items() if v is not None}
        self.session.add(
            WorkflowEvent(
                conversation_id=conversation.id, event_type=event_type, data=clean, request_id=self.request_id
            )
        )

    def _add_message(
        self,
        conversation: Conversation,
        role: MessageRole,
        content: str,
        idempotency_key: str | None = None,
        reply_to: uuid.UUID | None = None,
    ) -> Message:
        seq = (conversation.messages[-1].seq + 1) if conversation.messages else 1
        message = Message(
            id=uuid.uuid4(),
            seq=seq,
            role=role,
            content=content,
            idempotency_key=idempotency_key,
            reply_to_id=reply_to,
        )
        conversation.messages.append(message)
        return message

    def _save_state(self, conversation: Conversation, state: PatientState) -> None:
        data = state.model_dump(mode="json")
        if conversation.patient_state is None:
            conversation.patient_state = PatientStateRow(state=data)
        else:
            conversation.patient_state.state = data

    def _save_decision(self, conversation: Conversation, d: JevDecision, final: FinalDecision) -> JevDecisionRow:
        row = JevDecisionRow(
            conversation_id=conversation.id,
            action=d.action,
            department=d.department,
            urgency=d.urgency,
            complexity=d.complexity,
            missing_info=d.missing_info,
            action_confidence=d.action_confidence,
            department_confidence=d.department_confidence,
            human_review_probability=d.human_review_probability,
            final_action=final.action,
            final_department=final.department,
            final_urgency=final.urgency,
            final_complexity=final.complexity,
            human_review_recommended=final.human_review_recommended,
            emergency=final.emergency,
            crisis_support=final.crisis_support,
            policy_overrides=[o.__dict__ for o in final.overrides],
            provider=d.provider,
            model_version=d.model,
            request_id=d.request_id,
            latency_ms=d.latency_ms,
            input_tokens=d.input_tokens,
            probabilities=d.probabilities,
            raw_request=d.raw_request,
            raw_response=d.raw_response,
        )
        self.session.add(row)
        return row

    async def _replay(self, conversation: Conversation, key: str) -> TurnResult | None:
        user = next((m for m in conversation.messages if m.idempotency_key == key), None)
        if user is None:
            return None
        reply = next((m for m in conversation.messages if m.reply_to_id == user.id), None)
        if reply is None:
            return None
        return TurnResult(
            conversation,
            reply,
            self.state_of(conversation),
            await self.latest_decision(conversation.id),
            replayed=True,
        )

    async def _record_llm_failure(self, conversation_id: uuid.UUID, exc: LLMUnavailableError) -> None:
        await self.session.rollback()
        self.session.add(
            WorkflowEvent(
                conversation_id=conversation_id,
                event_type=E.LLM_FAILED,
                data={"reason": exc.reason},
                request_id=self.request_id,
            )
        )
        await self.session.commit()
        log.warning(
            "llm.extract.failed", conversation_id=str(conversation_id), request_id=self.request_id, reason=exc.reason
        )

    @staticmethod
    def _upstream_error(exc: LLMUnavailableError) -> UpstreamUnavailableError:
        if isinstance(exc, LLMRateLimitedError) and (exc.retry_after_seconds or 0) > DAILY_QUOTA_RETRY_AFTER_SECONDS:
            # A long Retry-After means the free-tier daily quota is exhausted, not a momentary spike.
            return UpstreamUnavailableError(
                "DEMO_DAILY_LIMIT",
                "The demo has reached today's usage limit. Please come back tomorrow.",
                exc.retry_after_seconds,
                retryable=False,
            )
        if isinstance(exc, LLMRateLimitedError):
            return UpstreamUnavailableError(
                "LLM_RATE_LIMITED",
                "The assistant is busy right now. Please try again in a moment.",
                exc.retry_after_seconds,
            )
        return UpstreamUnavailableError("LLM_UNAVAILABLE", "The assistant couldn't respond. Please try again.")


def _flag_sources(new_flags: list[Any], rule_flags: list[Any], llm_flags: list[Any]) -> list[str]:
    sources = []
    if any(f in rule_flags for f in new_flags):
        sources.append("rules")
    if any(f in llm_flags for f in new_flags):
        sources.append("llm")
    return sources
