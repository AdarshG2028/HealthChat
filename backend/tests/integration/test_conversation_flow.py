"""End-to-end over HTTP with mock providers. Asserts behaviour AND the API-call budget via spans."""

import httpx
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.jev.mock_provider import MockJevDecisionProvider
from app.llm.mock_provider import MockLLMProvider
from tests.conftest import Chat, span_names, spans_named

STOMACH = ["I've had stomach pain since yesterday.", "About 5.", "It comes and goes", "some nausea"]


async def test_gathering_turns_make_one_llm_call_and_no_jev_call(
    client: httpx.AsyncClient, spans: InMemorySpanExporter
) -> None:
    cid = (await client.post("/api/conversation/start")).json()["id"]
    spans.clear()
    resp = await client.post(f"/api/conversation/{cid}/message", json={"content": STOMACH[0]})
    body = resp.json()

    assert body["status"] == "COLLECTING_INFORMATION"
    assert "scale" in body["message"]["content"]
    assert body["recommendation"] is None
    names = span_names(spans)
    assert names.count("llm.extract") == 1
    assert "jev.evaluate" not in names
    assert "llm.response" not in names


async def test_full_flow_reaches_recommendation_with_exactly_one_jev_call(
    chat: Chat,
    client: httpx.AsyncClient,
    spans: InMemorySpanExporter,
    jev: MockJevDecisionProvider,
    llm: MockLLMProvider,
) -> None:
    cid, body = await chat(*STOMACH)

    assert body["status"] == "COMPLETED"
    rec = body["recommendation"]
    assert rec["department"] == "GASTROENTEROLOGY"
    assert rec["urgency"] == "ROUTINE"
    assert rec["department_label"] == "Gastroenterology"
    assert "probabilities" not in rec  # never shown to end users
    assert jev.calls == 1
    assert llm.calls == len(STOMACH) + 1  # one per turn + one explanation
    assert len(spans_named(spans, "jev.evaluate")) == 1

    decision_turn = [s for s in spans_named(spans, "conversation.request")][-1]
    children = {
        s.name for s in spans.get_finished_spans() if s.parent and s.parent.span_id == decision_turn.context.span_id
    }
    assert {"llm.extract", "state.update", "jev.evaluate", "workflow.execute", "llm.response"} <= children

    # Closed after completion.
    again = await client.post(f"/api/conversation/{cid}/message", json={"content": "hello?"})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "CONVERSATION_CLOSED"


async def test_emergency_on_first_message_short_circuits(
    chat: Chat, jev: MockJevDecisionProvider, llm: MockLLMProvider, spans: InMemorySpanExporter
) -> None:
    _, body = await chat("I have crushing chest pain spreading to my left arm")

    assert body["emergency"] is True
    assert body["status"] == "COMPLETED"
    assert body["recommendation"]["department"] == "EMERGENCY"
    assert body["recommendation"]["urgency"] == "EMERGENCY"
    assert "emergency" in body["message"]["content"].lower()
    assert jev.calls == 1
    assert llm.calls == 1  # extraction only: emergencies never wait on an explanation call
    assert "llm.response" not in span_names(spans)


async def test_emergency_still_handled_when_llm_is_down(
    chat: Chat, client: httpx.AsyncClient, llm: MockLLMProvider
) -> None:
    llm.fail_mode = "error"
    cid, body = await chat("my dad's face is drooping and his speech is slurred")
    assert body["emergency"] is True
    assert body["recommendation"]["department"] == "EMERGENCY"
    trace = (await client.get(f"/api/conversation/{cid}/trace")).json()
    failed = [e for e in trace["events"] if e["type"] == "LLM_FAILED"]
    assert failed and failed[0]["data"]["continued"] == "red_flag_rules", "the failure must be visible in the trace"
    assert trace["api_calls"] == {"llm": 1, "jev": 1}


async def test_daily_quota_exhaustion_is_not_presented_as_retryable(
    client: httpx.AsyncClient, llm: MockLLMProvider
) -> None:
    cid = (await client.post("/api/conversation/start")).json()["id"]
    llm.fail_mode = "daily_quota"
    resp = await client.post(f"/api/conversation/{cid}/message", json={"content": STOMACH[0]})
    assert resp.status_code == 503
    err = resp.json()["error"]
    assert err["code"] == "DEMO_DAILY_LIMIT"
    assert err["retryable"] is False


async def test_llm_failure_rolls_back_turn_and_retry_works(client: httpx.AsyncClient, llm: MockLLMProvider) -> None:
    cid = (await client.post("/api/conversation/start")).json()["id"]
    llm.fail_mode = "rate_limit"
    failed = await client.post(f"/api/conversation/{cid}/message", json={"content": STOMACH[0]})
    assert failed.status_code == 503
    err = failed.json()["error"]
    assert err["code"] == "LLM_RATE_LIMITED" and err["retryable"] is True
    assert failed.headers["Retry-After"] == "2"

    llm.fail_mode = "none"
    ok = await client.post(f"/api/conversation/{cid}/message", json={"content": STOMACH[0]})
    assert ok.status_code == 200
    convo = (await client.get(f"/api/conversation/{cid}")).json()
    assert [m["role"] for m in convo["messages"]] == ["assistant", "user", "assistant"], "no duplicate user message"
    trace = (await client.get(f"/api/conversation/{cid}/trace")).json()
    assert "LLM_FAILED" in [e["type"] for e in trace["events"]]


async def test_jev_failure_gives_safe_fallback_and_can_be_retried(
    chat: Chat, client: httpx.AsyncClient, jev: MockJevDecisionProvider
) -> None:
    jev.fail_mode = "timeout"
    cid, body = await chat(*STOMACH)
    assert body["status"] == "ERROR"
    assert body["message"]["content"].startswith("Automated decision unavailable")
    assert body["recommendation"] is None

    jev.fail_mode = "none"
    retried = await client.post(f"/api/conversation/{cid}/decision/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "COMPLETED"
    second = await client.post(f"/api/conversation/{cid}/decision/retry")
    assert second.status_code == 409


async def test_invalid_jev_output_is_never_executed(chat: Chat, jev: MockJevDecisionProvider) -> None:
    jev.fail_mode = "invalid"
    _, body = await chat(*STOMACH)
    assert body["status"] == "ERROR"
    assert body["recommendation"] is None


async def test_explanation_failure_falls_back_to_template(
    chat: Chat, llm: MockLLMProvider, client: httpx.AsyncClient
) -> None:
    cid = (await client.post("/api/conversation/start")).json()["id"]
    for text in STOMACH[:-1]:
        await client.post(f"/api/conversation/{cid}/message", json={"content": text})
    llm.fail_mode = "explain_error"
    body = (await client.post(f"/api/conversation/{cid}/message", json={"content": STOMACH[-1]})).json()
    assert body["status"] == "COMPLETED"
    assert "gastroenterology" in body["message"]["content"].lower()
    trace = (await client.get(f"/api/conversation/{cid}/trace")).json()
    assert "EXPLANATION_FALLBACK_USED" in [e["type"] for e in trace["events"]]


async def test_idempotent_retry_does_not_call_models_again(client: httpx.AsyncClient, llm: MockLLMProvider) -> None:
    cid = (await client.post("/api/conversation/start")).json()["id"]
    headers = {"Idempotency-Key": "abc-123"}
    first = await client.post(f"/api/conversation/{cid}/message", json={"content": STOMACH[0]}, headers=headers)
    calls = llm.calls
    second = await client.post(f"/api/conversation/{cid}/message", json={"content": STOMACH[0]}, headers=headers)
    assert second.status_code == 200
    assert second.json()["replayed"] is True
    assert second.json()["message"]["id"] == first.json()["message"]["id"]
    assert llm.calls == calls


async def test_jev_ask_more_information_loop(
    chat: Chat, client: httpx.AsyncClient, jev: MockJevDecisionProvider
) -> None:
    """Jev asks for onset once (headache); backend turns it into a question; next turn decides again."""
    cid, body = await chat("I've had a headache for 2 days", "about 6 out of 10", "it comes and goes", "no")
    assert body["status"] == "COLLECTING_INFORMATION"
    assert body["message"]["content"] == "Did it start suddenly, or come on gradually?"
    assert body["recommendation"] is None
    assert jev.calls == 1

    body = (await client.post(f"/api/conversation/{cid}/message", json={"content": "gradually"})).json()
    assert body["status"] == "COMPLETED"
    assert body["recommendation"]["department"] == "NEUROLOGY"
    assert jev.calls == 2

    trace = (await client.get(f"/api/conversation/{cid}/trace")).json()
    assert trace["workflow_path"].count("JEV_PROCESSING") == 2
    assert "EXECUTING_ACTION" in trace["workflow_path"]


async def test_turn_cap_forces_a_decision(chat: Chat, jev: MockJevDecisionProvider) -> None:
    _, body = await chat(*["hmm"] * 8)
    assert body["status"] in {"COMPLETED", "ESCALATED", "ERROR"}
    assert jev.calls >= 1


async def test_correction_reevaluates_at_most_once(
    chat: Chat, client: httpx.AsyncClient, jev: MockJevDecisionProvider
) -> None:
    cid, _ = await chat(*STOMACH)
    assert jev.calls == 1

    # Non-decision-relevant correction: no Jev call.
    resp = await client.patch(f"/api/conversation/{cid}/state", json={"current_medications": ["antacids"]})
    assert resp.status_code == 200 and jev.calls == 1

    # Decision-relevant correction: exactly one re-evaluation.
    resp = await client.patch(
        f"/api/conversation/{cid}/state", json={"primary_symptoms": ["skin rash"], "associated_symptoms": ["itching"]}
    )
    assert resp.status_code == 200
    assert resp.json()["recommendation"]["department"] == "DERMATOLOGY"
    assert jev.calls == 2

    resp = await client.patch(f"/api/conversation/{cid}/state", json={"primary_symptoms": ["cough"]})
    assert resp.status_code == 409
    assert jev.calls == 2


async def test_trace_is_built_from_stored_data_only(
    chat: Chat, client: httpx.AsyncClient, jev: MockJevDecisionProvider, llm: MockLLMProvider
) -> None:
    cid, _ = await chat(*STOMACH)
    before = (jev.calls, llm.calls)
    trace = (await client.get(f"/api/conversation/{cid}/trace")).json()
    assert (jev.calls, llm.calls) == before, "trace must not call any model"

    assert trace["workflow_path"] == [
        "COLLECTING_INFORMATION",
        "READY_FOR_DECISION",
        "JEV_PROCESSING",
        "EXECUTING_ACTION",
        "COMPLETED",
    ]
    assert trace["api_calls"] == {"llm": len(STOMACH) + 1, "jev": 1}
    decision = trace["decisions"][0]
    assert decision["probabilities"]["department"]["GASTROENTEROLOGY"] > 0.5
    assert set(decision["jev_request"]["questions"]) >= {"action", "department", "urgency", "needs_human_review"}
    types = [e["type"] for e in trace["events"]]
    assert types.index("READY_FOR_JEV") < types.index("JEV_DECISION_COMPLETED") < types.index("CONVERSATION_COMPLETED")


async def test_request_id_propagates(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/conversation/start", headers={"X-Request-ID": "req-from-client"})
    assert resp.headers["X-Request-ID"] == "req-from-client"
    trace = (await client.get(f"/api/conversation/{resp.json()['id']}/trace")).json()
    assert trace["events"][0]["request_id"] == "req-from-client"


async def test_no_patient_text_in_span_attributes(chat: Chat, spans: InMemorySpanExporter) -> None:
    await chat(*STOMACH)
    for span in spans.get_finished_spans():
        for value in (span.attributes or {}).values():
            assert "stomach" not in str(value).lower() and "nausea" not in str(value).lower()


async def test_unknown_conversation_is_404(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/conversation/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


async def test_reset_creates_a_fresh_conversation(chat: Chat, client: httpx.AsyncClient) -> None:
    cid, _ = await chat(*STOMACH)
    fresh = await client.post(f"/api/conversation/{cid}/reset")
    assert fresh.status_code == 201
    assert fresh.json()["id"] != cid and fresh.json()["status"] == "COLLECTING_INFORMATION"
    assert (await client.get(f"/api/conversation/{cid}")).json()["status"] == "COMPLETED"
