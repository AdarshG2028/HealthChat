"""Deterministic post-Jev safety & reconciliation policy.

Jev answers its questions in parallel, so combinations can be incoherent (e.g. DERMATOLOGY
with EMERGENCY urgency). This layer makes the final decision coherent and safe:

* urgency is never downgraded,
* emergency red flags always win,
* low confidence or a high human-review probability escalates to a human,
* the ASK_MORE_INFORMATION loop is bounded.

Every override is returned so it can be recorded in the Decision Trace.
"""

from dataclasses import dataclass, field

from app.domain.enums import Complexity, Department, RedFlag, Urgency, WorkflowAction, WorkflowState
from app.jev.types import JevDecision


@dataclass(frozen=True)
class PolicyOverride:
    rule: str
    field: str
    before: str
    after: str


@dataclass(frozen=True)
class PolicyConfig:
    confidence_threshold: float = 0.6
    human_review_threshold: float = 0.5
    max_ask_more_rounds: int = 1


@dataclass
class FinalDecision:
    action: WorkflowAction
    department: Department
    urgency: Urgency
    complexity: Complexity
    human_review_recommended: bool
    emergency: bool
    crisis_support: bool
    overrides: list[PolicyOverride] = field(default_factory=list)

    @property
    def next_state(self) -> WorkflowState:
        if self.action == WorkflowAction.ASK_MORE_INFORMATION:
            return WorkflowState.COLLECTING_INFORMATION
        if self.action == WorkflowAction.ESCALATE_TO_HUMAN:
            return WorkflowState.ESCALATED
        return WorkflowState.COMPLETED

    def _set(self, rule: str, name: str, value: object) -> None:
        before = getattr(self, name)
        if before != value:
            self.overrides.append(PolicyOverride(rule, name, str(before), str(value)))
            setattr(self, name, value)


def apply_policy(
    decision: JevDecision,
    *,
    red_flags: list[RedFlag],
    ask_more_rounds_used: int,
    turn_cap_reached: bool,
    config: PolicyConfig,
) -> FinalDecision:
    final = FinalDecision(
        action=decision.action,
        department=decision.department,
        urgency=decision.urgency,
        complexity=decision.complexity,
        human_review_recommended=decision.human_review_probability >= config.human_review_threshold,
        emergency=False,
        crisis_support=RedFlag.SUICIDAL_IDEATION in red_flags,
    )

    # 1. Emergency red flags always win and are never downgraded.
    if red_flags:
        final._set("red_flag_emergency", "urgency", Urgency.EMERGENCY)

    # 2. Coherence: EMERGENCY urgency <-> EMERGENCY department, never lowering urgency.
    if final.department == Department.EMERGENCY:
        final._set(
            "emergency_department_implies_emergency_urgency", "urgency", Urgency.max(final.urgency, Urgency.EMERGENCY)
        )
    if final.urgency == Urgency.EMERGENCY:
        final.emergency = True
        final._set("emergency_urgency_routes_to_emergency", "department", Department.EMERGENCY)
        final._set("emergency_urgency_routes_to_emergency", "action", WorkflowAction.ROUTE_TO_DEPARTMENT)
        final._set("emergency_is_complex", "complexity", Complexity.COMPLEX)
        # Emergencies go straight to emergency care; human review is flagged, not awaited.
        # Crisis support (self-harm) additionally surfaces crisis-line resources in the UI.
        if final.crisis_support:
            final.human_review_recommended = True
        return final

    # 3. Bounded ASK_MORE_INFORMATION loop.
    if final.action == WorkflowAction.ASK_MORE_INFORMATION and (
        ask_more_rounds_used >= config.max_ask_more_rounds or turn_cap_reached
    ):
        final._set("ask_more_budget_exhausted", "action", WorkflowAction.REFER_TO_DOCTOR)
        final._set("ask_more_budget_exhausted", "department", Department.GENERAL_MEDICINE)
    if final.action == WorkflowAction.ASK_MORE_INFORMATION:
        return final

    # 4. Confidence gating (TypeSafe confidence-gated routing pattern).
    low_confidence = (
        decision.action_confidence < config.confidence_threshold
        or decision.department_confidence < config.confidence_threshold
    )
    if low_confidence:
        final._set("low_confidence_escalation", "action", WorkflowAction.ESCALATE_TO_HUMAN)
        final.human_review_recommended = True
    elif final.human_review_recommended:
        final._set("human_review_probability_escalation", "action", WorkflowAction.ESCALATE_TO_HUMAN)

    # 5. Routing to a department requires a concrete department.
    if final.action == WorkflowAction.ROUTE_TO_DEPARTMENT and final.department == Department.OTHER:
        final._set("route_needs_department", "action", WorkflowAction.REFER_TO_DOCTOR)
        final._set("route_needs_department", "department", Department.GENERAL_MEDICINE)

    return final
