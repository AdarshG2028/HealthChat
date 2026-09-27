"""Deterministic emergency red-flag rules.

These run on every user message at zero API cost, alongside the LLM's own `red_flags`
output. Either source forces an immediate decision. They are deliberately conservative
(a false positive shows an emergency banner; a false negative can hurt someone), with a
small negation guard so "no chest pain" does not trigger.
"""

import re
from dataclasses import dataclass

from app.domain.enums import RedFlag


@dataclass(frozen=True)
class _Rule:
    flag: RedFlag
    pattern: re.Pattern[str]


def _p(*alternatives: str) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{a})" for a in alternatives), re.IGNORECASE)


_RULES: tuple[_Rule, ...] = (
    _Rule(
        RedFlag.CHEST_PAIN_CARDIAC,
        _p(
            r"chest (?:pain|pressure|tightness)\b.{0,60}\b(?:arm|jaw|neck|shoulder|sweat|sweating|breath)",
            r"(?:crushing|squeezing|heavy) (?:chest|pain in (?:my|the) chest)",
            r"heart attack",
        ),
    ),
    _Rule(
        RedFlag.STROKE_SIGNS,
        _p(
            r"face (?:is )?droop",
            r"(?:slurred|slurring) (?:speech|words)",
            r"(?:sudden(?:ly)?|can'?t move|cannot move).{0,30}(?:numb|weak|paraly[sz])\w*.{0,30}(?:one side|arm|leg|face)",
            r"worst headache of my life",
            r"\bstroke\b",
        ),
    ),
    _Rule(
        RedFlag.BREATHING_DIFFICULTY,
        _p(
            r"can'?t breathe",
            r"cannot breathe",
            r"unable to breathe",
            r"struggling to breathe",
            r"gasping for (?:air|breath)",
            r"lips (?:are |turning )?(?:blue|purple)",
        ),
    ),
    _Rule(
        RedFlag.SUICIDAL_IDEATION,
        _p(
            r"(?:kill|hurt|harm) myself",
            r"suicid\w*",
            r"end (?:my|it all)(?: life)?\b",
            r"don'?t want to (?:live|be alive)",
            r"better off dead",
        ),
    ),
    _Rule(
        RedFlag.ANAPHYLAXIS,
        _p(
            r"(?:throat|tongue|lips?) (?:is |are |feels? )?(?:swelling|swollen|closing)",
            r"anaphyla\w*",
        ),
    ),
    _Rule(
        RedFlag.SEVERE_BLEEDING,
        _p(
            r"(?:won'?t|will not|can'?t|cannot) stop bleeding",
            r"bleeding (?:heavily|a lot|profusely)",
            r"(?:vomiting|coughing (?:up)?) blood",
        ),
    ),
    _Rule(
        RedFlag.LOSS_OF_CONSCIOUSNESS,
        _p(r"passed out", r"fainted", r"lost consciousness", r"unconscious", r"blacked out"),
    ),
    _Rule(RedFlag.SEIZURE, _p(r"seizure", r"convuls\w*", r"\bfits?\b(?: of shaking)?")),
)

_NEGATION = re.compile(
    r"\b(?:no|not|never|denies|deny|without|don'?t have|doesn'?t have)\b[\w\s,']{0,20}$", re.IGNORECASE
)


def detect_red_flags(*texts: str) -> list[RedFlag]:
    """Return red flags found in the given texts, in rule order, without duplicates."""
    found: list[RedFlag] = []
    for text in texts:
        for rule in _RULES:
            if rule.flag in found:
                continue
            for match in rule.pattern.finditer(text):
                preceding = text[max(0, match.start() - 30) : match.start()]
                if not _NEGATION.search(preceding):
                    found.append(rule.flag)
                    break
    return found
