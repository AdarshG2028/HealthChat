"""Map an SDK `SystemOneResponse` onto our closed `JevDecision` vocabulary.

Any label outside our enums raises `InvalidJevOutputError`: arbitrary model strings never
flow into the workflow.
"""

from enum import StrEnum
from typing import Any

from typesafe_sdk import ChoiceAnswer, SystemOneResponse

from app.domain.enums import Complexity, Department, MissingInfo, Urgency, WorkflowAction
from app.jev.types import InvalidJevOutputError, JevDecision


def _choice[E: StrEnum](response: SystemOneResponse, key: str, enum: type[E]) -> tuple[E, ChoiceAnswer]:
    answer = response.choices.get(key)
    if answer is None:
        raise InvalidJevOutputError(f"missing choice answer '{key}'")
    try:
        return enum(answer.choice), answer
    except ValueError as exc:
        raise InvalidJevOutputError(f"unknown label for '{key}'") from exc


def map_response(
    response: SystemOneResponse,
    *,
    provider: str,
    latency_ms: int,
    request_id: str | None,
    raw_request: dict[str, Any],
) -> JevDecision:
    action, action_ans = _choice(response, "action", WorkflowAction)
    department, dept_ans = _choice(response, "department", Department)
    urgency, urg_ans = _choice(response, "urgency", Urgency)
    complexity, cx_ans = _choice(response, "complexity", Complexity)
    missing, missing_ans = _choice(response, "missing_info", MissingInfo)

    review = response.nouls.get("needs_human_review")
    if review is None:
        raise InvalidJevOutputError("missing noul answer 'needs_human_review'")
    if not 0.0 <= review.noul <= 1.0:
        raise InvalidJevOutputError("human review probability out of range")

    return JevDecision(
        action=action,
        action_confidence=action_ans.confidence,
        department=department,
        department_confidence=dept_ans.confidence,
        urgency=urgency,
        urgency_confidence=urg_ans.confidence,
        complexity=complexity,
        complexity_confidence=cx_ans.confidence,
        human_review_probability=review.noul,
        missing_info=missing,
        probabilities={
            "action": dict(action_ans.probabilities),
            "department": dict(dept_ans.probabilities),
            "urgency": dict(urg_ans.probabilities),
            "complexity": dict(cx_ans.probabilities),
            "missing_info": dict(missing_ans.probabilities),
        },
        provider=provider,
        model=response.model,
        request_id=request_id,
        latency_ms=latency_ms,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        raw_request=raw_request,
        raw_response=response.model_dump(mode="json", include={"model", "usage", "answers"}),
    )
