"""Explicit, bounded workflow state machine. Illegal transitions raise instead of drifting."""

from app.domain.enums import WorkflowState as S

ALLOWED_TRANSITIONS: dict[S, frozenset[S]] = {
    S.COLLECTING_INFORMATION: frozenset({S.COLLECTING_INFORMATION, S.READY_FOR_DECISION, S.ERROR}),
    S.READY_FOR_DECISION: frozenset({S.JEV_PROCESSING, S.ERROR}),
    S.JEV_PROCESSING: frozenset({S.EXECUTING_ACTION, S.ERROR}),
    # EXECUTING_ACTION -> COLLECTING_INFORMATION is the bounded ASK_MORE_INFORMATION loop.
    S.EXECUTING_ACTION: frozenset({S.COMPLETED, S.ESCALATED, S.COLLECTING_INFORMATION, S.ERROR}),
    # Terminal states can only re-enter the decision via a bounded correction / retry.
    S.COMPLETED: frozenset({S.READY_FOR_DECISION}),
    S.ESCALATED: frozenset({S.READY_FOR_DECISION}),
    S.ERROR: frozenset({S.READY_FOR_DECISION}),
}


class IllegalTransitionError(Exception):
    def __init__(self, current: S, target: S) -> None:
        super().__init__(f"Illegal workflow transition {current} -> {target}")
        self.current = current
        self.target = target


def transition(current: S, target: S) -> S:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise IllegalTransitionError(current, target)
    return target
