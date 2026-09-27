from typing import Any

from app.domain.enums import Complexity, Department, MissingInfo, RedFlag, Urgency, WorkflowAction, WorkflowState
from app.jev.types import JevDecision
from app.safety.policy import PolicyConfig, apply_policy

CONFIG = PolicyConfig(confidence_threshold=0.6, human_review_threshold=0.5, max_ask_more_rounds=1)


def decision(**overrides: Any) -> JevDecision:
    base: dict[str, Any] = dict(
        action=WorkflowAction.ROUTE_TO_DEPARTMENT,
        action_confidence=0.9,
        department=Department.GASTROENTEROLOGY,
        department_confidence=0.9,
        urgency=Urgency.ROUTINE,
        urgency_confidence=0.9,
        complexity=Complexity.MODERATE,
        complexity_confidence=0.8,
        human_review_probability=0.1,
        missing_info=MissingInfo.NONE,
        provider="test",
        model="t",
    )
    return JevDecision(**(base | overrides))


def run(d: JevDecision, red_flags: list[RedFlag] | None = None, rounds: int = 0, cap: bool = False):  # type: ignore[no-untyped-def]
    return apply_policy(d, red_flags=red_flags or [], ask_more_rounds_used=rounds, turn_cap_reached=cap, config=CONFIG)


def test_clean_decision_passes_through() -> None:
    final = run(decision())
    assert (final.action, final.department, final.urgency) == (
        WorkflowAction.ROUTE_TO_DEPARTMENT,
        Department.GASTROENTEROLOGY,
        Urgency.ROUTINE,
    )
    assert final.overrides == []
    assert final.next_state == WorkflowState.COMPLETED


def test_red_flag_forces_emergency_pathway() -> None:
    final = run(decision(), red_flags=[RedFlag.CHEST_PAIN_CARDIAC])
    assert final.emergency
    assert (final.department, final.urgency, final.action) == (
        Department.EMERGENCY,
        Urgency.EMERGENCY,
        WorkflowAction.ROUTE_TO_DEPARTMENT,
    )
    assert {o.rule for o in final.overrides} >= {"red_flag_emergency"}


def test_incoherent_emergency_urgency_with_specialty_is_reconciled() -> None:
    final = run(decision(department=Department.DERMATOLOGY, urgency=Urgency.EMERGENCY))
    assert final.department == Department.EMERGENCY and final.emergency


def test_emergency_department_never_downgrades_urgency() -> None:
    final = run(decision(department=Department.EMERGENCY, urgency=Urgency.ROUTINE))
    assert final.urgency == Urgency.EMERGENCY


def test_low_confidence_escalates_to_human() -> None:
    final = run(decision(department_confidence=0.45))
    assert final.action == WorkflowAction.ESCALATE_TO_HUMAN
    assert final.human_review_recommended
    assert final.next_state == WorkflowState.ESCALATED


def test_high_human_review_probability_escalates() -> None:
    final = run(decision(human_review_probability=0.8))
    assert final.action == WorkflowAction.ESCALATE_TO_HUMAN


def test_ask_more_is_allowed_once_then_bounded() -> None:
    ask = decision(action=WorkflowAction.ASK_MORE_INFORMATION, missing_info=MissingInfo.DURATION)
    assert run(ask, rounds=0).next_state == WorkflowState.COLLECTING_INFORMATION
    exhausted = run(ask, rounds=1)
    assert exhausted.action == WorkflowAction.REFER_TO_DOCTOR
    assert run(ask, cap=True).action == WorkflowAction.REFER_TO_DOCTOR


def test_route_to_other_department_becomes_gp_referral() -> None:
    final = run(decision(department=Department.OTHER))
    assert (final.action, final.department) == (WorkflowAction.REFER_TO_DOCTOR, Department.GENERAL_MEDICINE)


def test_suicidal_ideation_sets_crisis_support() -> None:
    final = run(decision(), red_flags=[RedFlag.SUICIDAL_IDEATION])
    assert final.crisis_support and final.emergency and final.human_review_recommended
