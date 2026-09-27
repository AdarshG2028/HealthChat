"""Deterministic mock Jev. Same input -> same decision, no network, no credits."""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from app.domain.enums import Complexity, Department, MissingInfo, Urgency, WorkflowAction
from app.jev.questions import build_questions, build_state
from app.jev.types import InvalidJevOutputError, JevCaseInput, JevDecision, JevUnavailableError

MockFailMode = Literal["none", "timeout", "error", "invalid"]


@dataclass(frozen=True)
class Scenario:
    action: WorkflowAction
    department: Department
    urgency: Urgency
    complexity: Complexity
    human_review: float
    confidence: float = 0.86
    missing: MissingInfo = MissingInfo.NONE


A, D, U, C = WorkflowAction, Department, Urgency, Complexity

EMERGENCY = Scenario(A.ROUTE_TO_DEPARTMENT, D.EMERGENCY, U.EMERGENCY, C.COMPLEX, 0.71, 0.93)
ASK_DURATION = Scenario(
    A.ASK_MORE_INFORMATION, D.GENERAL_MEDICINE, U.ROUTINE, C.SIMPLE, 0.12, 0.74, MissingInfo.DURATION
)
# Headaches: sudden vs gradual onset matters (thunderclap headache), so Jev asks once.
ASK_ONSET = Scenario(A.ASK_MORE_INFORMATION, D.NEUROLOGY, U.ROUTINE, C.MODERATE, 0.15, 0.72, MissingInfo.ONSET)
COMPLEX_HISTORY = Scenario(A.ESCALATE_TO_HUMAN, D.OTHER, U.URGENT, C.COMPLEX, 0.82, 0.48)
DEFAULT = Scenario(A.REFER_TO_DOCTOR, D.GENERAL_MEDICINE, U.ROUTINE, C.MODERATE, 0.22, 0.71)

# Ordered keyword table: first match wins.
KEYWORD_SCENARIOS: tuple[tuple[tuple[str, ...], Scenario], ...] = (
    (
        ("stomach", "abdominal", "abdomen", "nausea", "diarrh", "vomit", "constipat"),
        Scenario(A.ROUTE_TO_DEPARTMENT, D.GASTROENTEROLOGY, U.ROUTINE, C.MODERATE, 0.18),
    ),
    (
        ("high fever", "fever", "urinary", "burning when"),
        Scenario(A.REFER_TO_DOCTOR, D.GENERAL_MEDICINE, U.URGENT, C.MODERATE, 0.27, 0.79),
    ),
    (
        ("cold", "runny nose", "sore throat", "sneez", "blocked nose"),
        Scenario(A.PROVIDE_GENERAL_GUIDANCE, D.GENERAL_MEDICINE, U.ROUTINE, C.SIMPLE, 0.06, 0.9),
    ),
    (
        ("rash", "itch", "skin", "acne", "hives"),
        Scenario(A.ROUTE_TO_DEPARTMENT, D.DERMATOLOGY, U.ROUTINE, C.SIMPLE, 0.09),
    ),
    (
        ("headache", "migraine", "dizz", "numb"),
        Scenario(A.ROUTE_TO_DEPARTMENT, D.NEUROLOGY, U.ROUTINE, C.MODERATE, 0.24, 0.77),
    ),
    (
        ("back pain", "knee", "joint", "sprain", "shoulder", "ankle"),
        Scenario(A.ROUTE_TO_DEPARTMENT, D.ORTHOPEDICS, U.ROUTINE, C.SIMPLE, 0.1),
    ),
    (
        ("cough", "wheez", "breathless", "short of breath"),
        Scenario(A.ROUTE_TO_DEPARTMENT, D.PULMONOLOGY, U.ROUTINE, C.MODERATE, 0.2, 0.8),
    ),
    (("ear", "sinus", "tonsil"), Scenario(A.ROUTE_TO_DEPARTMENT, D.ENT, U.ROUTINE, C.SIMPLE, 0.08)),
)


def pick_scenario(case: JevCaseInput) -> Scenario:
    state = case.patient_state
    if case.red_flags:
        return EMERGENCY
    if not state.symptom_duration and case.ask_more_rounds_used == 0:
        return ASK_DURATION
    symptoms = " ".join(state.primary_symptoms).lower()
    if "headache" in symptoms and not state.symptom_onset and case.ask_more_rounds_used == 0:
        return ASK_ONSET
    if len(state.existing_conditions) >= 2:
        return COMPLEX_HISTORY
    text = " ".join(state.primary_symptoms + state.associated_symptoms).lower()
    for keywords, scenario in KEYWORD_SCENARIOS:
        # Word-start match so "ear" does not match "heart" or "year".
        if any(re.search(rf"\b{re.escape(k)}", text) for k in keywords):
            return scenario
    return DEFAULT


def _distribution(chosen: StrEnum, enum: type[StrEnum], confidence: float) -> dict[str, float]:
    others = [e for e in enum if e != chosen]
    rest = round((1 - confidence) / len(others), 4)
    return {str(e): (confidence if e == chosen else rest) for e in enum}


class MockJevDecisionProvider:
    name = "mock-jev"

    def __init__(self, fail_mode: MockFailMode = "none") -> None:
        self.fail_mode = fail_mode
        self.calls = 0

    async def evaluate_case(self, case: JevCaseInput) -> JevDecision:
        self.calls += 1
        if self.fail_mode == "timeout":
            raise JevUnavailableError("timeout")
        if self.fail_mode == "error":
            raise JevUnavailableError("TypeSafeInternalServerError", retryable=False)
        if self.fail_mode == "invalid":
            raise InvalidJevOutputError("unknown label for 'department'")

        s = pick_scenario(case)
        probabilities = {
            "action": _distribution(s.action, WorkflowAction, s.confidence),
            "department": _distribution(s.department, Department, s.confidence),
            "urgency": _distribution(s.urgency, Urgency, 0.88),
            "complexity": _distribution(s.complexity, Complexity, 0.8),
            "missing_info": _distribution(s.missing, MissingInfo, 0.7),
        }
        questions = build_questions()
        return JevDecision(
            action=s.action,
            action_confidence=s.confidence,
            department=s.department,
            department_confidence=s.confidence,
            urgency=s.urgency,
            urgency_confidence=0.88,
            complexity=s.complexity,
            complexity_confidence=0.8,
            human_review_probability=s.human_review,
            missing_info=s.missing,
            probabilities=probabilities,
            provider=self.name,
            model="mock-jev-1",
            request_id=f"mock-{self.calls}",
            latency_ms=0,
            input_tokens=None,
            raw_request={
                "state": build_state(case),
                "questions": {k: q.model_dump(mode="json", exclude_none=True) for k, q in questions.items()},
            },
            raw_response={"model": "mock-jev-1", "scenario": s.action.value},
        )

    async def aclose(self) -> None:
        return None
