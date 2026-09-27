"""LIVE smoke tests. THESE CONSUME REAL API CREDITS / RATE LIMIT.

Never run by default (excluded via `-m 'not live'` and network is blocked). Run manually:

    uv run pytest -m live --force-enable-socket tests/live -s

Cost of one full run: 1 Jev `system_one` call (~1k input tokens, ~$0.00004) + 2 Groq requests
(one structured turn, one explanation).
The Jev test records the real response to tests/fixtures/recorded/ so the offline mapper
tests run against the true wire format from then on.
"""

import json
from pathlib import Path

import pytest

from app.config import Settings
from app.domain.patient_state import PatientState
from app.jev.mapper import map_response
from app.jev.questions import build_questions, build_state
from app.jev.types import JevCaseInput
from app.llm.types import TurnContext

pytestmark = [pytest.mark.live, pytest.mark.enable_socket]


def show(text: str) -> None:
    """Print safely on consoles without UTF-8 (e.g. Windows cp1252); models emit typographic characters."""
    print(text.encode("ascii", "replace").decode("ascii"))

# Keys come from backend/.env (or the environment), exactly like the app.
SETTINGS = Settings()
RECORDED_DIR = Path(__file__).parents[1] / "fixtures" / "recorded"

CASE = JevCaseInput(
    patient_state=PatientState(
        primary_symptoms=["stomach pain"],
        symptom_duration="since yesterday",
        symptom_severity="5/10",
        symptom_frequency="comes and goes",
        associated_symptoms=["nausea"],
    ),
    turn_count=4,
)


@pytest.mark.skipif(SETTINGS.typesafe_api_key is None, reason="TYPESAFE_API_KEY not set")
async def test_jev_live_single_call_and_record_fixture() -> None:
    from typesafe_sdk import AsyncTypeSafeClient

    assert SETTINGS.typesafe_api_key is not None
    async with AsyncTypeSafeClient(
        api_key=SETTINGS.typesafe_api_key.get_secret_value(), model=SETTINGS.jev_model
    ) as client:
        response = await client.system_one(state=build_state(CASE), questions=build_questions())

    RECORDED_DIR.mkdir(parents=True, exist_ok=True)
    raw = json.loads(response.raw_http_response.content)
    (RECORDED_DIR / "jev_system_one_response.json").write_text(json.dumps(raw, indent=2))

    decision = map_response(response, provider="jev", latency_ms=0, request_id=response.request_id, raw_request={})
    show(
        f"\nJev {decision.model}: {decision.action} / {decision.department} / {decision.urgency} "
        f"(conf {decision.action_confidence:.2f}, review {decision.human_review_probability:.2f})"
    )


@pytest.mark.skipif(SETTINGS.groq_api_key is None, reason="GROQ_API_KEY not set")
async def test_groq_live_single_structured_turn() -> None:
    from app.llm.groq_provider import GroqLLMProvider

    llm = GroqLLMProvider(
        api_key=SETTINGS.groq_api_key.get_secret_value(),  # type: ignore[union-attr]
        model=SETTINGS.llm_model,
        timeout_seconds=30,
    )
    try:
        result = await llm.extract_turn(
            TurnContext(
                patient_state=PatientState(),
                recent_messages=[],
                user_message="I've had stomach pain since yesterday.",
                turn=1,
                max_turns=8,
            )
        )
    finally:
        await llm.aclose()
    assert result.output.extracted.primary_symptoms
    show(
        f"\nGroq {result.meta.model}: next question -> {result.output.next_question!r} "
        f"({result.meta.input_tokens} in / {result.meta.output_tokens} out tokens)"
    )


@pytest.mark.skipif(SETTINGS.groq_api_key is None, reason="GROQ_API_KEY not set")
async def test_groq_live_explanation_is_complete() -> None:
    """Verifies the shipped explanation path, incl. that hidden reasoning fits the token budget."""
    from app.domain.enums import Complexity, Department, Urgency, WorkflowAction
    from app.llm.groq_provider import GroqLLMProvider
    from app.llm.types import ExplanationContext

    llm = GroqLLMProvider(
        api_key=SETTINGS.groq_api_key.get_secret_value(),  # type: ignore[union-attr]
        model=SETTINGS.llm_model,
        timeout_seconds=30,
    )
    try:
        result = await llm.explain_decision(
            ExplanationContext(
                action=WorkflowAction.ROUTE_TO_DEPARTMENT,
                department=Department.GASTROENTEROLOGY,
                urgency=Urgency.ROUTINE,
                complexity=Complexity.MODERATE,
                human_review_recommended=False,
                emergency=False,
                patient_state=CASE.patient_state,
            )
        )
    finally:
        await llm.aclose()
    show(
        f"\nExplanation ({len(result.text)} chars, {result.meta.output_tokens} completion tokens incl. reasoning):"
        f"\n{result.text}"
    )
