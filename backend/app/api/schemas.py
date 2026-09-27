"""HTTP DTOs. These generate the OpenAPI schema the frontend's TypeScript types come from.

User-facing views never include raw model probabilities (§22); the developer trace does.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.db.models import Conversation, JevDecisionRow, Message, WorkflowEvent
from app.domain.enums import (
    Complexity,
    Department,
    MessageRole,
    MissingInfo,
    RedFlag,
    Urgency,
    WorkflowAction,
    WorkflowEventType,
    WorkflowState,
)
from app.domain.patient_state import PatientState
from app.llm import templates


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class MessageOut(BaseModel):
    id: uuid.UUID
    role: MessageRole
    content: str
    created_at: datetime

    @classmethod
    def of(cls, m: Message) -> "MessageOut":
        return cls(id=m.id, role=MessageRole(m.role), content=m.content, created_at=m.created_at)


class Progress(BaseModel):
    turn: int
    max_turns: int
    collected_fields: list[str]
    core_complete: bool


class Recommendation(BaseModel):
    action: WorkflowAction
    department: Department
    department_label: str
    urgency: Urgency
    complexity: Complexity
    next_step: str
    human_review_recommended: bool
    emergency: bool
    crisis_support: bool
    decided_at: datetime

    @classmethod
    def of(cls, row: JevDecisionRow) -> "Recommendation":
        action, dept, urgency = (
            WorkflowAction(row.final_action),
            Department(row.final_department),
            Urgency(row.final_urgency),
        )
        return cls(
            action=action,
            department=dept,
            department_label=templates.DEPARTMENT_LABELS[dept],
            urgency=urgency,
            complexity=Complexity(row.final_complexity),
            next_step=templates.next_step_text(action, dept, urgency),
            human_review_recommended=row.human_review_recommended,
            emergency=row.emergency,
            crisis_support=row.crisis_support,
            decided_at=row.created_at,
        )


class ConversationView(BaseModel):
    id: uuid.UUID
    status: WorkflowState
    messages: list[MessageOut]
    patient_state: PatientState
    progress: Progress
    recommendation: Recommendation | None
    emergency: bool = Field(description="True as soon as any red flag is detected; independent of Jev/LLM.")
    created_at: datetime


class TurnResponse(BaseModel):
    conversation_id: uuid.UUID
    status: WorkflowState
    message: MessageOut
    patient_state: PatientState
    progress: Progress
    recommendation: Recommendation | None
    emergency: bool
    replayed: bool = False


class DecisionOut(BaseModel):
    """Developer view of a stored Jev decision (includes probabilities)."""

    id: uuid.UUID
    action: WorkflowAction
    department: Department
    urgency: Urgency
    complexity: Complexity
    missing_info: MissingInfo
    action_confidence: float
    department_confidence: float
    human_review_probability: float
    final_action: WorkflowAction
    final_department: Department
    final_urgency: Urgency
    final_complexity: Complexity
    human_review_recommended: bool
    emergency: bool
    policy_overrides: list[dict[str, Any]]
    probabilities: dict[str, dict[str, float]]
    provider: str
    model_version: str
    request_id: str | None
    latency_ms: int
    input_tokens: int | None
    jev_request: dict[str, Any]
    created_at: datetime

    @classmethod
    def of(cls, r: JevDecisionRow) -> "DecisionOut":
        return cls(
            id=r.id,
            action=WorkflowAction(r.action),
            department=Department(r.department),
            urgency=Urgency(r.urgency),
            complexity=Complexity(r.complexity),
            missing_info=MissingInfo(r.missing_info),
            action_confidence=r.action_confidence,
            department_confidence=r.department_confidence,
            human_review_probability=r.human_review_probability,
            final_action=WorkflowAction(r.final_action),
            final_department=Department(r.final_department),
            final_urgency=Urgency(r.final_urgency),
            final_complexity=Complexity(r.final_complexity),
            human_review_recommended=r.human_review_recommended,
            emergency=r.emergency,
            policy_overrides=r.policy_overrides,
            probabilities=r.probabilities,
            provider=r.provider,
            model_version=r.model_version,
            request_id=r.request_id,
            latency_ms=r.latency_ms,
            input_tokens=r.input_tokens,
            jev_request=r.raw_request,
            created_at=r.created_at,
        )


class TraceEvent(BaseModel):
    id: int
    type: WorkflowEventType
    data: dict[str, Any]
    request_id: str | None
    created_at: datetime

    @classmethod
    def of(cls, e: WorkflowEvent) -> "TraceEvent":
        return cls(
            id=e.id, type=WorkflowEventType(e.event_type), data=e.data, request_id=e.request_id, created_at=e.created_at
        )


class ApiCallCounts(BaseModel):
    llm: int
    jev: int


class DecisionTrace(BaseModel):
    """Everything the developer Decision Trace shows. Built from stored data: zero model calls."""

    conversation_id: uuid.UUID
    status: WorkflowState
    llm_provider: str
    jev_provider: str
    turn_count: int
    created_at: datetime
    workflow_path: list[WorkflowState]
    red_flags: list[RedFlag]
    information_available: list[str]
    api_calls: ApiCallCounts
    decisions: list[DecisionOut]
    events: list[TraceEvent]


class ErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool = False
    request_id: str | None = None
    retry_after_seconds: float | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


def progress_of(conversation: Conversation, state: PatientState, max_turns: int) -> Progress:
    return Progress(
        turn=conversation.turn_count,
        max_turns=max_turns,
        collected_fields=state.filled_fields(),
        core_complete=state.has_minimum_core(),
    )
