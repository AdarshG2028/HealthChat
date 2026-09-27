from app.domain.enums import RedFlag
from app.domain.patient_state import PatientState, PatientStateUpdate


def test_merge_sets_scalars_and_unions_lists_case_insensitively() -> None:
    state = PatientState(primary_symptoms=["Stomach pain"])
    new, changed = state.merge(
        PatientStateUpdate(symptom_duration="since yesterday", primary_symptoms=["stomach pain", "nausea"])
    )
    assert new.symptom_duration == "since yesterday"
    assert new.primary_symptoms == ["Stomach pain", "nausea"]
    assert set(changed) == {"symptom_duration", "primary_symptoms"}


def test_merge_never_erases_with_none_or_empty() -> None:
    state = PatientState(symptom_severity="5/10", associated_symptoms=["nausea"])
    new, changed = state.merge(PatientStateUpdate(symptom_severity=None, associated_symptoms=[]))
    assert new == state
    assert changed == []


def test_merge_ignores_blank_strings() -> None:
    new, changed = PatientState().merge(PatientStateUpdate(symptom_duration="   "))
    assert new.symptom_duration is None and changed == []


def test_correction_replaces_lists_and_can_clear_scalars() -> None:
    state = PatientState(associated_symptoms=["nausea", "fever"], symptom_severity="8/10")
    new, changed = state.correct(PatientStateUpdate(associated_symptoms=["nausea"], symptom_severity=None))
    assert new.associated_symptoms == ["nausea"]
    assert new.symptom_severity is None
    assert set(changed) == {"associated_symptoms", "symptom_severity"}


def test_minimum_core_and_missing_fields() -> None:
    state = PatientState(primary_symptoms=["headache"], symptom_duration="2 days")
    assert not state.has_minimum_core()
    assert state.missing_core_fields() == ["symptom_severity"]
    assert state.model_copy(update={"symptom_severity": "mild"}).has_minimum_core()


def test_add_red_flags_reports_only_new_ones() -> None:
    state = PatientState(red_flags=[RedFlag.SEIZURE])
    new, added = state.add_red_flags([RedFlag.SEIZURE, RedFlag.STROKE_SIGNS])
    assert added == [RedFlag.STROKE_SIGNS]
    assert new.red_flags == [RedFlag.SEIZURE, RedFlag.STROKE_SIGNS]
