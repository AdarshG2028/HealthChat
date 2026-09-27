"""Deterministic user-facing text. Zero API calls; used as fallbacks and for fixed steps."""

from app.domain.enums import Department, MissingInfo, Urgency, WorkflowAction
from app.domain.patient_state import PatientState

GREETING = (
    "Hi, I'm here to help you figure out a sensible next step for your health concern. "
    "I can't diagnose anything, but I'll ask a few short questions and suggest where to go from here. "
    "What's been bothering you?"
)

EMERGENCY_NOTICE = (
    "Some of what you describe can be a sign of a medical emergency. Please call your local emergency "
    "number (for example 112 / 911 / 999) or go to the nearest emergency department now."
)

CRISIS_NOTICE = (
    "If you are thinking about harming yourself, you don't have to go through this alone. Please contact "
    "your local emergency number or a crisis line right now (for example 988 in the US, 116 123 in the UK "
    "and EU, or 14416 Tele-MANAS in India)."
)

_CORE_QUESTIONS = {
    "primary_symptoms": "Could you tell me a bit more about the main symptom that's bothering you?",
    "symptom_duration": "How long have you been experiencing this?",
    "symptom_severity": "How severe would you say it is, for example on a scale from 1 to 10?",
}

_MISSING_INFO_QUESTIONS = {
    MissingInfo.DURATION: "How long have you been experiencing this?",
    MissingInfo.SEVERITY: "How severe is it right now, on a scale from 1 to 10?",
    MissingInfo.ONSET: "Did it start suddenly, or come on gradually?",
    MissingInfo.ASSOCIATED_SYMPTOMS: "Have you noticed any other symptoms along with it?",
    MissingInfo.MEDICAL_HISTORY: "Do you have any existing health conditions I should know about?",
    MissingInfo.MEDICATIONS: "Are you currently taking any medications?",
    MissingInfo.AGE_OR_SEX: "Could you share your age and sex? It helps suggest the right kind of care.",
    MissingInfo.NONE: "Is there anything else about how you're feeling that you think is important?",
}

DEPARTMENT_LABELS = {
    Department.GENERAL_MEDICINE: "General Medicine",
    Department.CARDIOLOGY: "Cardiology",
    Department.NEUROLOGY: "Neurology",
    Department.PULMONOLOGY: "Pulmonology",
    Department.GASTROENTEROLOGY: "Gastroenterology",
    Department.ORTHOPEDICS: "Orthopedics",
    Department.DERMATOLOGY: "Dermatology",
    Department.ENT: "Ear, Nose & Throat",
    Department.GYNECOLOGY: "Gynecology",
    Department.UROLOGY: "Urology",
    Department.EMERGENCY: "Emergency Department",
    Department.OTHER: "an appropriate specialist",
}

_URGENCY_PHRASES = {
    Urgency.ROUTINE: "in the coming days",
    Urgency.URGENT: "within the next 24 to 48 hours",
    Urgency.EMERGENCY: "immediately",
}

_SAFETY_NET = (
    "If your symptoms suddenly get much worse, or you notice anything like chest pain, trouble breathing, "
    "fainting or confusion, seek emergency care right away."
)


def core_question(missing_field: str) -> str:
    return _CORE_QUESTIONS.get(missing_field, _MISSING_INFO_QUESTIONS[MissingInfo.NONE])


def ask_more_question(missing: MissingInfo) -> str:
    return _MISSING_INFO_QUESTIONS[missing]


def next_step_text(action: WorkflowAction, department: Department, urgency: Urgency) -> str:
    """Short, deterministic 'what to do next' line for the recommendation card."""
    when = _URGENCY_PHRASES[urgency]
    match action:
        case WorkflowAction.ROUTE_TO_DEPARTMENT if department == Department.EMERGENCY:
            return "Go to the nearest emergency department or call your local emergency number now."
        case WorkflowAction.ROUTE_TO_DEPARTMENT:
            return f"Book a consultation with {DEPARTMENT_LABELS[department]} {when}."
        case WorkflowAction.REFER_TO_DOCTOR:
            return f"Arrange to see a general physician {when}."
        case WorkflowAction.PROVIDE_GENERAL_GUIDANCE:
            return "Rest, stay hydrated and monitor your symptoms; see a doctor if they persist or worsen."
        case WorkflowAction.ESCALATE_TO_HUMAN:
            return f"Have your situation reviewed by a healthcare professional {when}."
        case _:
            return "No specific healthcare step seems necessary right now."


def explanation(action: WorkflowAction, department: Department, urgency: Urgency, state: PatientState) -> str:
    """Template fallback for the final LLM explanation. Never pretends a human reviewed anything."""
    symptoms = ", ".join(state.primary_symptoms) or "your symptoms"
    opener = f"Thank you for sharing the details about {symptoms}."
    if action == WorkflowAction.ESCALATE_TO_HUMAN:
        body = (
            "Based on what you've told me, your situation should be reviewed by a healthcare professional "
            "rather than handled by an automated suggestion. " + next_step_text(action, department, urgency)
        )
    elif department == Department.EMERGENCY:
        # No generic safety-net line here: it would tell someone already in an emergency to watch for one.
        return f"{opener} {EMERGENCY_NOTICE}"
    else:
        step = next_step_text(action, department, urgency)
        body = f"Based on the information you provided, {step[0].lower()}{step[1:]}"
    return f"{opener} {body} {_SAFETY_NET}"


def decision_unavailable(emergency: bool) -> str:
    """Shown when Jev fails. Safe fallback toward professional care; no fabricated decision."""
    if emergency:
        return f"Automated decision unavailable. {EMERGENCY_NOTICE}"
    return (
        "Automated decision unavailable right now. To be safe, please contact a doctor or your local health "
        f"service to discuss your symptoms. {_SAFETY_NET}"
    )
