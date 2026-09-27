"""LLM contract: one structured call per gathering turn, one text call per decision."""

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from app.domain.enums import Complexity, Department, RedFlag, Urgency, WorkflowAction
from app.domain.patient_state import PatientState, PatientStateUpdate


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class TurnContext(BaseModel):
    patient_state: PatientState
    recent_messages: list[ChatTurn]
    user_message: str
    turn: int
    max_turns: int


class LLMStateExtraction(BaseModel):
    """Wire schema for extracted facts. Every field is required (nullable) for strict mode."""

    model_config = ConfigDict(extra="forbid")

    age: int | None
    sex: Literal["female", "male", "other"] | None
    symptom_onset: str | None
    symptom_duration: str | None
    symptom_severity: str | None
    symptom_frequency: str | None
    primary_symptoms: list[str]
    associated_symptoms: list[str]
    existing_conditions: list[str]
    current_medications: list[str]
    known_allergies: list[str]
    relevant_medical_history: list[str]
    additional_information: list[str]


class LLMTurnOutput(BaseModel):
    """The single structured response of a gathering turn."""

    model_config = ConfigDict(extra="forbid")

    extracted: LLMStateExtraction
    red_flags: list[RedFlag]
    info_sufficient: bool
    next_question: str | None


class LLMCallMeta(BaseModel):
    provider: str
    model: str
    latency_ms: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None


class TurnExtraction(BaseModel):
    output: LLMTurnOutput
    meta: LLMCallMeta

    def to_update(self) -> PatientStateUpdate:
        data = self.output.extracted.model_dump()
        # Empty lists mean "nothing new" for a merge.
        return PatientStateUpdate.model_validate(
            {k: (v or None) if isinstance(v, list) else v for k, v in data.items()}
        )


class ExplanationContext(BaseModel):
    action: WorkflowAction
    department: Department
    urgency: Urgency
    complexity: Complexity
    human_review_recommended: bool
    emergency: bool
    patient_state: PatientState


class Explanation(BaseModel):
    text: str
    meta: LLMCallMeta


class LLMUnavailableError(Exception):
    def __init__(self, reason: str, *, retryable: bool = True) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable


class LLMRateLimitedError(LLMUnavailableError):
    def __init__(self, retry_after_seconds: float | None = None) -> None:
        super().__init__("rate_limited", retryable=True)
        self.retry_after_seconds = retry_after_seconds


class LLMInvalidOutputError(LLMUnavailableError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason, retryable=True)


class LLMProvider(Protocol):
    name: str
    model: str

    async def extract_turn(self, ctx: TurnContext) -> TurnExtraction: ...

    async def explain_decision(self, ctx: ExplanationContext) -> Explanation: ...

    async def aclose(self) -> None: ...


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic schema -> strict structured-output schema.

    Inlines `$ref`s, forces `additionalProperties: false` and all-required objects, and
    drops titles/defaults that strict decoders reject.
    """
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(defs[node["$ref"].split("/")[-1]])
            out = {k: resolve(v) for k, v in node.items() if k not in {"title", "default", "description"}}
            if out.get("type") == "object" and "properties" in out:
                out["additionalProperties"] = False
                out["required"] = list(out["properties"].keys())
            return out
        if isinstance(node, list):
            return [resolve(n) for n in node]
        return node

    resolved: dict[str, Any] = resolve(schema)
    return resolved


TURN_OUTPUT_SCHEMA: dict[str, Any] = strict_json_schema(LLMTurnOutput)
