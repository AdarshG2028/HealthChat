import pytest

from app.domain.enums import RedFlag
from app.safety.red_flags import detect_red_flags


@pytest.mark.parametrize(
    ("text", "flag"),
    [
        ("I have crushing chest pain", RedFlag.CHEST_PAIN_CARDIAC),
        ("chest pain that goes down my left arm", RedFlag.CHEST_PAIN_CARDIAC),
        ("my dad's face is drooping and his speech is slurred", RedFlag.STROKE_SIGNS),
        ("I suddenly feel numb on one side of my face", RedFlag.STROKE_SIGNS),
        ("I can't breathe properly", RedFlag.BREATHING_DIFFICULTY),
        ("I want to kill myself", RedFlag.SUICIDAL_IDEATION),
        ("my throat is swelling after eating peanuts", RedFlag.ANAPHYLAXIS),
        ("the cut won't stop bleeding", RedFlag.SEVERE_BLEEDING),
        ("I fainted this morning", RedFlag.LOSS_OF_CONSCIOUSNESS),
        ("she had a seizure", RedFlag.SEIZURE),
    ],
)
def test_detects_red_flags(text: str, flag: RedFlag) -> None:
    assert flag in detect_red_flags(text)


@pytest.mark.parametrize(
    "text",
    [
        "I've had stomach pain since yesterday",
        "no chest pain radiating to the arm",
        "I have never fainted",
        "mild headache, about 3 out of 10",
        "I'm breathing fine, just a cough",
    ],
)
def test_no_false_positives_on_common_or_negated_text(text: str) -> None:
    assert detect_red_flags(text) == []


def test_multiple_texts_deduplicated() -> None:
    assert detect_red_flags("I fainted", "I passed out again") == [RedFlag.LOSS_OF_CONSCIOUSNESS]
