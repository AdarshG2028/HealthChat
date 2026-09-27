"""The single Jev `system_one` request: every related decision in ONE call.

Jev answers questions in parallel, so each question must stand on its own; coherence
across answers is enforced afterwards by `app.safety.policy`. Criteria keys are exactly
our enum values so the mapper can validate them strictly.
"""

from typing import Any

from typesafe_sdk import Choice, Noul

from app.domain.enums import Complexity, Department, MissingInfo, Urgency, WorkflowAction
from app.jev.types import JevCaseInput

ACTION_CRITERIA: dict[str, str] = {
    WorkflowAction.ASK_MORE_INFORMATION: "Key facts needed to choose a safe pathway are still missing.",
    WorkflowAction.PROVIDE_GENERAL_GUIDANCE: "Mild, self-limiting issue suitable for self-care guidance with safety-net advice.",
    WorkflowAction.REFER_TO_DOCTOR: "Should see a general doctor / primary care, no specific specialty indicated.",
    WorkflowAction.ROUTE_TO_DEPARTMENT: "A specific specialty or emergency department is clearly appropriate.",
    WorkflowAction.ESCALATE_TO_HUMAN: "Unclear, conflicting, high-risk or unusual case that a healthcare professional should review.",
    WorkflowAction.END: "No health concern requiring any pathway (e.g. user has no symptoms).",
}

DEPARTMENT_CRITERIA: dict[str, str] = {
    Department.GENERAL_MEDICINE: "General or multi-system symptoms, primary care.",
    Department.CARDIOLOGY: "Heart-related symptoms: palpitations, chest pain of cardiac character.",
    Department.NEUROLOGY: "Headaches, dizziness, numbness, weakness, seizures, memory issues.",
    Department.PULMONOLOGY: "Cough, breathlessness, wheezing, lung problems.",
    Department.GASTROENTEROLOGY: "Abdominal pain, nausea, vomiting, diarrhea, constipation, digestive issues.",
    Department.ORTHOPEDICS: "Bone, joint, back, muscle or injury-related pain.",
    Department.DERMATOLOGY: "Skin, hair or nail problems: rashes, itching, lesions.",
    Department.ENT: "Ear, nose, throat or sinus problems.",
    Department.GYNECOLOGY: "Menstrual, pregnancy-related or female reproductive concerns.",
    Department.UROLOGY: "Urinary symptoms, kidney pain, male reproductive concerns.",
    Department.EMERGENCY: "Potentially life-threatening presentation needing immediate care.",
    Department.OTHER: "None of the listed departments fits.",
}

URGENCY_CRITERIA: dict[str, str] = {
    Urgency.ROUTINE: "Can wait for a regular appointment in the coming days or weeks.",
    Urgency.URGENT: "Should be seen within 24-48 hours.",
    Urgency.EMERGENCY: "Needs immediate emergency care now.",
}

COMPLEXITY_CRITERIA: dict[str, str] = {
    Complexity.SIMPLE: "Single, common, well-defined problem.",
    Complexity.MODERATE: "Several symptoms or relevant history, still a fairly clear picture.",
    Complexity.COMPLEX: "Multiple interacting conditions, unclear picture or significant risk factors.",
}

MISSING_INFO_CRITERIA: dict[str, str] = {
    MissingInfo.DURATION: "How long the symptoms have lasted.",
    MissingInfo.SEVERITY: "How severe the symptoms are.",
    MissingInfo.ONSET: "How and when the symptoms started (sudden vs gradual).",
    MissingInfo.ASSOCIATED_SYMPTOMS: "Other symptoms occurring together.",
    MissingInfo.MEDICAL_HISTORY: "Relevant existing conditions or history.",
    MissingInfo.MEDICATIONS: "Current medications.",
    MissingInfo.AGE_OR_SEX: "The patient's age or sex.",
    MissingInfo.NONE: "Nothing important is missing.",
}


def _plain(criteria: dict[str, str]) -> dict[str, str]:
    # StrEnum keys -> plain str so the SDK's strict models and JSON see exact labels.
    return {str(k): v for k, v in criteria.items()}


def build_questions() -> dict[str, Choice | Noul]:
    return {
        "action": Choice(
            instructions="Which next healthcare workflow step is most appropriate for this case?",
            criteria=_plain(ACTION_CRITERIA),
        ),
        "department": Choice(
            instructions="Which department best fits the patient's main problem?",
            criteria=_plain(DEPARTMENT_CRITERIA),
        ),
        "urgency": Choice(
            instructions="How urgently should this patient be seen by a healthcare professional?",
            criteria=_plain(URGENCY_CRITERIA),
        ),
        "complexity": Choice(
            instructions="How complex is this case?",
            criteria=_plain(COMPLEXITY_CRITERIA),
        ),
        "needs_human_review": Noul(
            instructions="Should a healthcare professional review this case before any automated recommendation?",
            criteria={
                "true": "The case is ambiguous, high-risk, contradictory or outside routine triage.",
                "false": "The case is clear enough for an automated pathway recommendation.",
            },
        ),
        "missing_info": Choice(
            instructions="What is the single most important piece of missing information, if any?",
            criteria=_plain(MISSING_INFO_CRITERIA),
        ),
    }


def build_state(case: JevCaseInput) -> dict[str, Any]:
    """The Jev `state`: structured, de-identified, compact."""
    state = case.patient_state.model_dump(exclude={"red_flags"}, exclude_none=True)
    state = {k: v for k, v in state.items() if v != []}
    return {
        "task": "Healthcare triage: choose the next workflow step for a patient. Not a diagnosis.",
        "patient": state,
        "red_flags_detected": [str(f) for f in case.red_flags],
        "conversation_turns": case.turn_count,
    }
