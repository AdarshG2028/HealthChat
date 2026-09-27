"""HTTP API (§33 + DECISIONS #8). Handlers are thin; the service owns the workflow."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    ApiCallCounts,
    ConversationView,
    DecisionOut,
    DecisionTrace,
    ErrorResponse,
    MessageOut,
    Recommendation,
    SendMessageRequest,
    TraceEvent,
    TurnResponse,
    progress_of,
)
from app.config import Settings
from app.domain.enums import WorkflowEventType as E
from app.domain.enums import WorkflowState
from app.domain.patient_state import PatientState, PatientStateUpdate
from app.services.conversation_service import ConversationService, TurnResult

router = APIRouter(prefix="/api/conversation", tags=["conversation"])

ERRORS: dict[int | str, dict[str, Any]] = {code: {"model": ErrorResponse} for code in (404, 409, 422, 429, 503)}


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_service(request: Request, session: Annotated[AsyncSession, Depends(get_session)]) -> ConversationService:
    return ConversationService(
        session,
        request.app.state.llm,
        request.app.state.jev,
        request.app.state.settings,
        request_id=getattr(request.state, "request_id", None),
    )


Service = Annotated[ConversationService, Depends(get_service)]


def _settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


async def _view(service: ConversationService, conversation_id: uuid.UUID, max_turns: int) -> ConversationView:
    conversation = await service.get(conversation_id)
    state = service.state_of(conversation)
    latest = await service.latest_decision(conversation.id)
    return ConversationView(
        id=conversation.id,
        status=WorkflowState(conversation.status),
        messages=[MessageOut.of(m) for m in conversation.messages],
        patient_state=state,
        progress=progress_of(conversation, state, max_turns),
        recommendation=_recommendation(conversation.status, latest),
        emergency=bool(state.red_flags),
        created_at=conversation.created_at,
    )


def _recommendation(status: str, row) -> Recommendation | None:  # type: ignore[no-untyped-def]
    # Only surface a recommendation once the workflow has actually reached an outcome.
    if row is None or WorkflowState(status) not in {WorkflowState.COMPLETED, WorkflowState.ESCALATED}:
        return None
    return Recommendation.of(row)


def _turn(result: TurnResult, max_turns: int) -> TurnResponse:
    c = result.conversation
    return TurnResponse(
        conversation_id=c.id,
        status=WorkflowState(c.status),
        message=MessageOut.of(result.assistant_message),
        patient_state=result.state,
        progress=progress_of(c, result.state, max_turns),
        recommendation=_recommendation(c.status, result.decision),
        emergency=bool(result.state.red_flags),
        replayed=result.replayed,
    )


@router.post("/start", response_model=ConversationView, status_code=201, responses=ERRORS)
async def start_conversation(request: Request, service: Service) -> ConversationView:
    client_ip = request.client.host if request.client else None
    result = await service.start(client_ip)
    await service.session.flush()
    return await _view(service, result.conversation.id, _settings(request).max_turns)


@router.post("/{conversation_id}/message", response_model=TurnResponse, responses=ERRORS)
async def send_message(
    conversation_id: uuid.UUID,
    body: SendMessageRequest,
    request: Request,
    service: Service,
    idempotency_key: Annotated[str | None, Header(max_length=64)] = None,
) -> TurnResponse:
    result = await service.handle_message(conversation_id, body.content.strip(), idempotency_key)
    return _turn(result, _settings(request).max_turns)


@router.get("/{conversation_id}", response_model=ConversationView, responses=ERRORS)
async def get_conversation(conversation_id: uuid.UUID, request: Request, service: Service) -> ConversationView:
    return await _view(service, conversation_id, _settings(request).max_turns)


@router.get("/{conversation_id}/state", response_model=PatientState, responses=ERRORS)
async def get_state(conversation_id: uuid.UUID, service: Service) -> PatientState:
    return service.state_of(await service.get(conversation_id))


@router.patch("/{conversation_id}/state", response_model=ConversationView, responses=ERRORS)
async def correct_state(
    conversation_id: uuid.UUID, corrections: PatientStateUpdate, request: Request, service: Service
) -> ConversationView:
    await service.correct_state(conversation_id, corrections)
    await service.session.flush()
    return await _view(service, conversation_id, _settings(request).max_turns)


@router.post("/{conversation_id}/decision/retry", response_model=TurnResponse, responses=ERRORS)
async def retry_decision(conversation_id: uuid.UUID, request: Request, service: Service) -> TurnResponse:
    return _turn(await service.retry_decision(conversation_id), _settings(request).max_turns)


@router.get("/{conversation_id}/decisions", response_model=list[DecisionOut], responses=ERRORS)
async def get_decisions(conversation_id: uuid.UUID, service: Service) -> list[DecisionOut]:
    await service.get(conversation_id)
    return [DecisionOut.of(d) for d in await service.decisions(conversation_id)]


@router.get("/{conversation_id}/trace", response_model=DecisionTrace, responses=ERRORS)
async def get_trace(conversation_id: uuid.UUID, service: Service) -> DecisionTrace:
    """Built entirely from stored events and decisions. Never calls Jev or the LLM."""
    conversation = await service.get(conversation_id)
    state = service.state_of(conversation)
    events = await service.events(conversation_id)
    path = [WorkflowState.COLLECTING_INFORMATION] + [
        WorkflowState(e.data["to_state"]) for e in events if e.event_type == E.WORKFLOW_STATE_CHANGED
    ]
    llm_calls = sum(e.event_type in {E.LLM_EXTRACTION, E.LLM_RESPONSE_GENERATED, E.LLM_FAILED} for e in events)
    llm_calls += sum(
        e.event_type == E.EXPLANATION_FALLBACK_USED and e.data.get("reason") != "emergency_template" for e in events
    )
    jev_calls = sum(
        e.event_type == E.JEV_DECISION_COMPLETED
        or (e.event_type == E.JEV_FAILED and e.data.get("reason") != "daily_cap")
        for e in events
    )
    return DecisionTrace(
        conversation_id=conversation.id,
        status=WorkflowState(conversation.status),
        llm_provider=conversation.llm_provider,
        jev_provider=conversation.jev_provider,
        turn_count=conversation.turn_count,
        created_at=conversation.created_at,
        workflow_path=path,
        red_flags=state.red_flags,
        information_available=state.filled_fields(),
        api_calls=ApiCallCounts(llm=llm_calls, jev=jev_calls),
        decisions=[DecisionOut.of(d) for d in await service.decisions(conversation_id)],
        events=[TraceEvent.of(e) for e in events],
    )


@router.post("/{conversation_id}/reset", response_model=ConversationView, status_code=201, responses=ERRORS)
async def reset_conversation(conversation_id: uuid.UUID, request: Request, service: Service) -> ConversationView:
    """Start a fresh conversation. The old one is kept intact for its audit trail."""
    await service.get(conversation_id)
    client_ip = request.client.host if request.client else None
    result = await service.start(client_ip, reset_from=conversation_id)
    await service.session.flush()
    return await _view(service, result.conversation.id, _settings(request).max_turns)
