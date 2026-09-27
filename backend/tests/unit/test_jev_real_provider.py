"""Exercise the REAL Jev provider + SDK decoding + mapper through a mock HTTP transport.

Uses the recorded response from the manual live run when present (tests/fixtures/recorded/),
otherwise a synthetic fixture in the documented wire format. No network, no credits.
"""

import json
from pathlib import Path
from typing import Any

import httpx2
import pytest

from app.domain.enums import Department, Urgency, WorkflowAction
from app.domain.patient_state import PatientState
from app.jev.questions import build_questions
from app.jev.real_provider import RealJevDecisionProvider
from app.jev.types import InvalidJevOutputError, JevCaseInput, JevUnavailableError

FIXTURES = Path(__file__).parents[1] / "fixtures"
RECORDED = FIXTURES / "recorded" / "jev_system_one_response.json"
SYNTHETIC = FIXTURES / "jev_system_one_response.synthetic.json"

CASE = JevCaseInput(
    patient_state=PatientState(
        primary_symptoms=["stomach pain"], symptom_duration="since yesterday", symptom_severity="5/10"
    ),
    turn_count=3,
)


def fixture_body() -> dict[str, Any]:
    return json.loads((RECORDED if RECORDED.exists() else SYNTHETIC).read_text())


def provider(handler: Any) -> RealJevDecisionProvider:
    return RealJevDecisionProvider(
        api_key="test-key", model="jev-latest", timeout_seconds=5, transport=httpx2.MockTransport(handler)
    )


async def test_maps_response_and_sends_one_request_with_all_questions() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=fixture_body(), headers={"x-typesafe-request-id": "req_test_1"})

    decision = await provider(handler).evaluate_case(CASE)

    assert len(seen) == 1, "exactly one Jev call per decision"
    sent = json.loads(seen[0].content)
    assert set(sent["questions"]) == set(build_questions())
    assert "stomach pain" in json.dumps(sent["state"])
    assert decision.request_id == "req_test_1"
    assert decision.action in set(WorkflowAction)
    assert decision.department in set(Department)
    assert decision.urgency in set(Urgency)
    assert 0 <= decision.human_review_probability <= 1
    assert set(decision.probabilities) == {"action", "department", "urgency", "complexity", "missing_info"}
    assert decision.raw_request["questions"]["action"]["type"] == "choice"


async def test_unknown_label_is_rejected() -> None:
    body = fixture_body()
    body["answers"]["department"]["choice"] = "ASTROLOGY"

    decision_call = provider(lambda r: httpx2.Response(200, json=body)).evaluate_case(CASE)
    with pytest.raises(InvalidJevOutputError):
        await decision_call


async def test_missing_answer_is_rejected() -> None:
    body = fixture_body()
    del body["answers"]["needs_human_review"]
    with pytest.raises(InvalidJevOutputError):
        await provider(lambda r: httpx2.Response(200, json=body)).evaluate_case(CASE)


async def test_server_error_becomes_unavailable_after_one_retry() -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(500, json={"detail": "boom"})

    with pytest.raises(JevUnavailableError):
        await provider(handler).evaluate_case(CASE)
    assert calls == 2, "initial attempt + at most one retry"


async def test_auth_error_is_not_retried() -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(401, json={"detail": "bad key"})

    with pytest.raises(JevUnavailableError) as exc:
        await provider(handler).evaluate_case(CASE)
    assert calls == 1
    assert not exc.value.retryable
