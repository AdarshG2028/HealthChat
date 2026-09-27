"""Deterministic mock LLM: keyword/regex extraction and scripted follow-up questions.

Good enough to drive the full product (chat UI, state, Jev, trace, errors) with zero API
calls. It reads the previous assistant question to interpret short answers like "About 5".
"""

import re
from typing import Literal

from app.domain.patient_state import PatientState
from app.llm import templates
from app.llm.types import (
    Explanation,
    ExplanationContext,
    LLMCallMeta,
    LLMInvalidOutputError,
    LLMRateLimitedError,
    LLMStateExtraction,
    LLMTurnOutput,
    LLMUnavailableError,
    TurnContext,
    TurnExtraction,
)
from app.safety.red_flags import detect_red_flags

MockLLMFailMode = Literal["none", "timeout", "error", "rate_limit", "daily_quota", "invalid", "explain_error"]

SYMPTOMS: tuple[tuple[str, str], ...] = (
    (r"stomach (?:pain|ache)|stomachache|abdominal pain|tummy (?:pain|ache)", "stomach pain"),
    (r"chest pain", "chest pain"),
    (r"headaches?|migraine", "headache"),
    (r"rash", "skin rash"),
    (r"itch\w*", "itching"),
    (r"cough\w*", "cough"),
    (r"fever|temperature", "fever"),
    (r"sore throat", "sore throat"),
    (r"runny nose|blocked nose|sneez\w*", "cold symptoms"),
    (r"back pain|backache", "back pain"),
    (r"knee pain", "knee pain"),
    (r"ear ?ache|ear pain", "ear pain"),
    (r"nause\w*|feel(?:ing)? sick", "nausea"),
    (r"vomit\w*|throwing up", "vomiting"),
    (r"diarrh\w*", "diarrhea"),
    (r"dizz\w*", "dizziness"),
    (r"short(?:ness)? of breath|breathless", "shortness of breath"),
    (r"tired|fatigue\w*|exhausted", "fatigue"),
)

DURATION = re.compile(
    r"(since (?:yesterday|last \w+|this morning|\w+day)|for (?:about |around )?(?:a |an |\d+ )\w+"
    r"|\d+ (?:hours?|days?|weeks?|months?) ago|(?:a|one|two|three|few|couple of) (?:days?|weeks?) now"
    r"|this morning|today|last night)",
    re.IGNORECASE,
)
SEVERITY_NUMERIC = re.compile(
    r"\b(10|[1-9])\s*(?:/|out of)\s*10\b|\b(?:about|around|maybe|a|like)\s+(10|[1-9])\b|^\s*(10|[1-9])\s*$",
    re.IGNORECASE,
)
SEVERITY_WORD = re.compile(r"\b(mild|moderate|severe|unbearable|bad)\b", re.IGNORECASE)
AGE = re.compile(r"\b(?:i'?m|i am|aged?)\s+(\d{1,3})\b|\b(\d{1,3})\s*(?:years? old|yo|y/o)\b", re.IGNORECASE)
FREQUENCY = re.compile(r"(constant\w*|all the time|comes and goes|on and off|intermittent\w*|every \w+)", re.IGNORECASE)
ONSET = re.compile(r"(sudden(?:ly)?|gradual(?:ly)?|out of nowhere|slowly)", re.IGNORECASE)
NEGATIVE = re.compile(r"^\s*(no|nope|none|nothing(?: else)?|not really)\b", re.IGNORECASE)

Q_SEVERITY = "How severe is it on a scale from 1 to 10?"
Q_FREQUENCY = "Is it constant, or does it come and go?"
Q_ASSOCIATED = "Have you noticed anything else along with it, like fever, nausea or changes in appetite?"
Q_DURATION = "How long have you been experiencing this?"
Q_SYMPTOM = "Could you describe the main symptom that's bothering you?"
NO_OTHER = "no other symptoms reported"


def _empty() -> dict[str, object]:
    return {
        f: None for f in ("age", "sex", "symptom_onset", "symptom_duration", "symptom_severity", "symptom_frequency")
    } | {
        f: []
        for f in (
            "primary_symptoms",
            "associated_symptoms",
            "existing_conditions",
            "current_medications",
            "known_allergies",
            "relevant_medical_history",
            "additional_information",
        )
    }


def extract(text: str, last_question: str, state: PatientState) -> LLMStateExtraction:
    out = _empty()
    found = [name for pattern, name in SYMPTOMS if re.search(pattern, text, re.IGNORECASE)]
    if found:
        if state.primary_symptoms:
            out["associated_symptoms"] = [s for s in found if s not in state.primary_symptoms]
        else:
            out["primary_symptoms"] = found[:1]
            out["associated_symptoms"] = found[1:]
    if m := DURATION.search(text):
        out["symptom_duration"] = m.group(1).lower()
    if m := SEVERITY_NUMERIC.search(text):
        out["symptom_severity"] = f"{next(g for g in m.groups() if g)}/10"
    elif m := SEVERITY_WORD.search(text):
        out["symptom_severity"] = m.group(1).lower()
    if m := FREQUENCY.search(text):
        out["symptom_frequency"] = m.group(1).lower()
    if m := ONSET.search(text):
        out["symptom_onset"] = "sudden" if m.group(1).lower().startswith(("sudden", "out of")) else "gradual"
    if m := AGE.search(text):
        out["age"] = int(next(g for g in m.groups() if g))
    if re.search(r"\b(female|woman|girl)\b", text, re.IGNORECASE):
        out["sex"] = "female"
    elif re.search(r"\b(male|man|guy|boy)\b", text, re.IGNORECASE):
        out["sex"] = "male"
    if last_question == Q_ASSOCIATED and NEGATIVE.search(text):
        out["additional_information"] = [NO_OTHER]
    return LLMStateExtraction.model_validate(out)


def next_question(state: PatientState) -> str | None:
    if not state.primary_symptoms:
        return Q_SYMPTOM
    if not state.symptom_duration:
        return Q_DURATION
    if not state.symptom_severity:
        return Q_SEVERITY
    painful = any(w in " ".join(state.primary_symptoms) for w in ("pain", "headache", "ache"))
    if painful and not state.symptom_frequency:
        return Q_FREQUENCY
    if not state.associated_symptoms and NO_OTHER not in state.additional_information:
        return Q_ASSOCIATED
    return None


class MockLLMProvider:
    name = "mock-llm"
    model = "mock-llm-1"

    def __init__(self, fail_mode: MockLLMFailMode = "none") -> None:
        self.fail_mode = fail_mode
        self.calls = 0

    async def extract_turn(self, ctx: TurnContext) -> TurnExtraction:
        self.calls += 1
        if self.fail_mode == "timeout":
            raise LLMUnavailableError("timeout")
        if self.fail_mode == "error":
            raise LLMUnavailableError("http_500")
        if self.fail_mode == "rate_limit":
            raise LLMRateLimitedError(retry_after_seconds=2)
        if self.fail_mode == "daily_quota":
            raise LLMRateLimitedError(retry_after_seconds=3600)
        if self.fail_mode == "invalid":
            raise LLMInvalidOutputError("turn output failed schema validation")

        last_question = next((m.content for m in reversed(ctx.recent_messages) if m.role == "assistant"), "")
        extracted = extract(ctx.user_message, last_question, ctx.patient_state)
        preview, _ = ctx.patient_state.merge(
            TurnExtraction(
                output=LLMTurnOutput(extracted=extracted, red_flags=[], info_sufficient=False, next_question=None),
                meta=self._meta(),
            ).to_update()
        )
        question = next_question(preview)
        return TurnExtraction(
            output=LLMTurnOutput(
                extracted=extracted,
                red_flags=detect_red_flags(ctx.user_message),
                info_sufficient=question is None,
                next_question=question,
            ),
            meta=self._meta(),
        )

    async def explain_decision(self, ctx: ExplanationContext) -> Explanation:
        self.calls += 1
        if self.fail_mode in {"explain_error", "rate_limit"}:
            raise (
                LLMRateLimitedError(retry_after_seconds=2)
                if self.fail_mode == "rate_limit"
                else LLMUnavailableError("http_500")
            )
        text = templates.explanation(ctx.action, ctx.department, ctx.urgency, ctx.patient_state)
        return Explanation(text=text, meta=self._meta())

    def _meta(self) -> LLMCallMeta:
        return LLMCallMeta(provider=self.name, model=self.model)

    async def aclose(self) -> None:
        return None
