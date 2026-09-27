"""Canonical structured patient state, owned by the backend (never by the LLM's memory)."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import RedFlag

Sex = Literal["female", "male", "other"]

LIST_FIELDS = (
    "primary_symptoms",
    "associated_symptoms",
    "existing_conditions",
    "current_medications",
    "known_allergies",
    "relevant_medical_history",
    "additional_information",
)
SCALAR_FIELDS = (
    "age",
    "sex",
    "symptom_onset",
    "symptom_duration",
    "symptom_severity",
    "symptom_frequency",
)
# Fields whose change can alter the Jev decision (used to decide whether a correction re-evaluates).
DECISION_RELEVANT_FIELDS = frozenset(
    {
        "age",
        "sex",
        "primary_symptoms",
        "symptom_duration",
        "symptom_severity",
        "associated_symptoms",
        "existing_conditions",
        "symptom_onset",
    }
)


class PatientStateUpdate(BaseModel):
    """A partial update. `None` means "no new information", never "erase"."""

    model_config = ConfigDict(extra="forbid")

    age: int | None = Field(default=None, ge=0, le=120)
    sex: Sex | None = None
    symptom_onset: str | None = None
    symptom_duration: str | None = None
    symptom_severity: str | None = None
    symptom_frequency: str | None = None
    primary_symptoms: list[str] | None = None
    associated_symptoms: list[str] | None = None
    existing_conditions: list[str] | None = None
    current_medications: list[str] | None = None
    known_allergies: list[str] | None = None
    relevant_medical_history: list[str] | None = None
    additional_information: list[str] | None = None


class PatientState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    age: int | None = Field(default=None, ge=0, le=120)
    sex: Sex | None = None
    symptom_onset: str | None = None
    symptom_duration: str | None = None
    symptom_severity: str | None = None
    symptom_frequency: str | None = None
    primary_symptoms: list[str] = Field(default_factory=list)
    associated_symptoms: list[str] = Field(default_factory=list)
    existing_conditions: list[str] = Field(default_factory=list)
    current_medications: list[str] = Field(default_factory=list)
    known_allergies: list[str] = Field(default_factory=list)
    relevant_medical_history: list[str] = Field(default_factory=list)
    additional_information: list[str] = Field(default_factory=list)
    red_flags: list[RedFlag] = Field(default_factory=list)

    def merge(self, update: PatientStateUpdate) -> tuple["PatientState", list[str]]:
        """Merge new information. Scalars overwrite when provided; lists are unioned.

        Returns the new state and the names of fields that actually changed.
        """
        data = self.model_dump()
        changed: list[str] = []
        for name in SCALAR_FIELDS:
            value = getattr(update, name)
            if isinstance(value, str):
                value = value.strip() or None
            if value is not None and value != data[name]:
                data[name] = value
                changed.append(name)
        for name in LIST_FIELDS:
            incoming = getattr(update, name)
            if not incoming:
                continue
            merged = _union(data[name], incoming)
            if merged != data[name]:
                data[name] = merged
                changed.append(name)
        return PatientState.model_validate(data), changed

    def correct(self, corrections: PatientStateUpdate) -> tuple["PatientState", list[str]]:
        """Apply user corrections. Unlike `merge`, provided lists *replace* the current value."""
        data = self.model_dump()
        changed: list[str] = []
        for name, value in corrections.model_dump(exclude_unset=True).items():
            if isinstance(value, list):
                value = _union([], value)
            if value != data[name]:
                data[name] = value
                changed.append(name)
        return PatientState.model_validate(data), changed

    def add_red_flags(self, flags: list[RedFlag]) -> tuple["PatientState", list[RedFlag]]:
        new = [f for f in flags if f not in self.red_flags]
        if not new:
            return self, []
        return self.model_copy(update={"red_flags": [*self.red_flags, *new]}), new

    def has_minimum_core(self) -> bool:
        return bool(self.primary_symptoms and self.symptom_duration and self.symptom_severity)

    def missing_core_fields(self) -> list[str]:
        missing = []
        if not self.primary_symptoms:
            missing.append("primary_symptoms")
        if not self.symptom_duration:
            missing.append("symptom_duration")
        if not self.symptom_severity:
            missing.append("symptom_severity")
        return missing

    def filled_fields(self) -> list[str]:
        filled = [n for n in SCALAR_FIELDS if getattr(self, n) is not None]
        filled += [n for n in LIST_FIELDS if getattr(self, n)]
        return filled

    def text_values(self) -> list[str]:
        """All free-text values; used to re-run deterministic red-flag rules after corrections."""
        values: list[Any] = [getattr(self, n) for n in SCALAR_FIELDS if isinstance(getattr(self, n), str)]
        for n in LIST_FIELDS:
            values.extend(getattr(self, n))
        return [str(v) for v in values]


def _union(existing: list[str], incoming: list[str]) -> list[str]:
    """Order-preserving, case-insensitive de-duplication."""
    seen = {item.casefold() for item in existing}
    result = list(existing)
    for item in incoming:
        item = item.strip()
        if item and item.casefold() not in seen:
            seen.add(item.casefold())
            result.append(item)
    return result
