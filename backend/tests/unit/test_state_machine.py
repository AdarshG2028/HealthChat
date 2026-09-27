import pytest

from app.domain.enums import WorkflowState as S
from app.domain.state_machine import ALLOWED_TRANSITIONS, IllegalTransitionError, transition


def test_happy_path() -> None:
    state = S.COLLECTING_INFORMATION
    for target in (S.READY_FOR_DECISION, S.JEV_PROCESSING, S.EXECUTING_ACTION, S.COMPLETED):
        state = transition(state, target)
    assert state == S.COMPLETED


def test_ask_more_information_loop_is_explicit() -> None:
    assert transition(S.EXECUTING_ACTION, S.COLLECTING_INFORMATION) == S.COLLECTING_INFORMATION


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.COLLECTING_INFORMATION, S.JEV_PROCESSING),  # cannot skip READY_FOR_DECISION
        (S.COLLECTING_INFORMATION, S.COMPLETED),
        (S.JEV_PROCESSING, S.COLLECTING_INFORMATION),  # no Jev <-> LLM loops
        (S.COMPLETED, S.COLLECTING_INFORMATION),
        (S.ESCALATED, S.COMPLETED),
    ],
)
def test_illegal_transitions_raise(current: S, target: S) -> None:
    with pytest.raises(IllegalTransitionError):
        transition(current, target)


def test_every_state_has_rules() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(S)
