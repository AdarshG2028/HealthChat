"""Typed Jev decision contract used by the rest of the app (independent of the SDK)."""

from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.domain.enums import Complexity, Department, MissingInfo, RedFlag, Urgency, WorkflowAction
from app.domain.patient_state import PatientState


class JevCaseInput(BaseModel):
    """What we send to Jev: de-identified structured state only, never the raw transcript."""

    patient_state: PatientState
    red_flags: list[RedFlag] = Field(default_factory=list)
    turn_count: int
    ask_more_rounds_used: int = 0


class JevDecision(BaseModel):
    action: WorkflowAction
    action_confidence: float
    department: Department
    department_confidence: float
    urgency: Urgency
    urgency_confidence: float
    complexity: Complexity
    complexity_confidence: float
    human_review_probability: float
    missing_info: MissingInfo
    # Per-question probability distributions, kept for the Decision Trace.
    probabilities: dict[str, dict[str, float]] = Field(default_factory=dict)

    provider: str
    model: str
    request_id: str | None = None
    latency_ms: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw_request: dict[str, Any] = Field(default_factory=dict)
    raw_response: dict[str, Any] = Field(default_factory=dict)


class JevUnavailableError(Exception):
    """Jev could not produce a decision (timeout, API error, daily cap...)."""

    def __init__(self, reason: str, *, retryable: bool = True) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable


class InvalidJevOutputError(JevUnavailableError):
    """Jev answered, but the answer is outside our closed vocabulary."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason, retryable=False)


class JevDecisionProvider(Protocol):
    name: str

    async def evaluate_case(self, case: JevCaseInput) -> JevDecision: ...

    async def aclose(self) -> None: ...
