"""LLM layer: strict schema, Groq provider via mock transport, deterministic mock script."""

import json
from typing import Any

import httpx
import pytest

from app.domain.enums import Complexity, Department, RedFlag, Urgency, WorkflowAction
from app.domain.patient_state import PatientState
from app.llm.groq_provider import GroqLLMProvider
from app.llm.mock_provider import MockLLMProvider
from app.llm.types import (
    TURN_OUTPUT_SCHEMA,
    ChatTurn,
    ExplanationContext,
    LLMInvalidOutputError,
    LLMRateLimitedError,
    LLMUnavailableError,
    TurnContext,
)


def test_turn_schema_is_strict_mode_compatible() -> None:
    def walk(node: Any) -> None:
        if isinstance(node, dict):
            assert "$ref" not in node and "$defs" not in node
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(TURN_OUTPUT_SCHEMA)
    assert set(TURN_OUTPUT_SCHEMA["properties"]) == {"extracted", "red_flags", "info_sufficient", "next_question"}


VALID_OUTPUT = {
    "extracted": {
        "age": None,
        "sex": None,
        "symptom_onset": None,
        "symptom_duration": "since yesterday",
        "symptom_severity": None,
        "symptom_frequency": None,
        "primary_symptoms": ["stomach pain"],
        "associated_symptoms": [],
        "existing_conditions": [],
        "current_medications": [],
        "known_allergies": [],
        "relevant_medical_history": [],
        "additional_information": [],
    },
    "red_flags": [],
    "info_sufficient": False,
    "next_question": "How severe is the pain on a scale from 1 to 10?",
}

CTX = TurnContext(
    patient_state=PatientState(), recent_messages=[], user_message="stomach pain since yesterday", turn=1, max_turns=8
)


def completion(content: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "openai/gpt-oss-120b",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 600, "completion_tokens": 80, "total_tokens": 680},
    }


def groq_with(handler: Any) -> GroqLLMProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GroqLLMProvider(api_key="test", model="openai/gpt-oss-120b", timeout_seconds=5, http_client=client)


async def test_groq_extract_turn_sends_strict_schema_and_parses() -> None:
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=completion(json.dumps(VALID_OUTPUT)))

    result = await groq_with(handler).extract_turn(CTX)

    assert len(requests) == 1
    body = requests[0]
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["reasoning_effort"] == "low"
    assert "<user_message>" in body["messages"][-1]["content"]
    assert result.output.extracted.primary_symptoms == ["stomach pain"]
    assert result.meta.input_tokens == 600


async def test_groq_rate_limit_is_typed_and_not_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, json={"error": {"message": "slow down"}}, headers={"retry-after": "7"})

    with pytest.raises(LLMRateLimitedError) as exc:
        await groq_with(handler).extract_turn(CTX)
    assert exc.value.retry_after_seconds == 7
    assert calls == 1


async def test_groq_invalid_json_is_typed() -> None:
    with pytest.raises(LLMInvalidOutputError):
        await groq_with(lambda r: httpx.Response(200, json=completion("not json"))).extract_turn(CTX)


async def test_groq_truncated_output_is_rejected() -> None:
    body = completion("Based on what you told me, you should book a consultation with")
    body["choices"][0]["finish_reason"] = "length"
    ctx = ExplanationContext(
        action=WorkflowAction.REFER_TO_DOCTOR,
        department=Department.GENERAL_MEDICINE,
        urgency=Urgency.ROUTINE,
        complexity=Complexity.SIMPLE,
        human_review_recommended=False,
        emergency=False,
        patient_state=PatientState(),
    )
    with pytest.raises(LLMInvalidOutputError):
        await groq_with(lambda r: httpx.Response(200, json=body)).explain_decision(ctx)


async def test_groq_server_error_is_unavailable() -> None:
    with pytest.raises(LLMUnavailableError):
        await groq_with(lambda r: httpx.Response(503, json={})).extract_turn(CTX)


async def test_groq_explanation_rejects_empty_text() -> None:
    ctx = ExplanationContext(
        action=WorkflowAction.REFER_TO_DOCTOR,
        department=Department.GENERAL_MEDICINE,
        urgency=Urgency.ROUTINE,
        complexity=Complexity.SIMPLE,
        human_review_recommended=False,
        emergency=False,
        patient_state=PatientState(),
    )
    with pytest.raises(LLMInvalidOutputError):
        await groq_with(lambda r: httpx.Response(200, json=completion(""))).explain_decision(ctx)


async def test_mock_llm_follows_the_spec_script() -> None:
    """§17: stomach pain -> severity -> constant/intermittent -> associated symptoms -> sufficient."""
    llm = MockLLMProvider()
    state = PatientState()
    history: list[ChatTurn] = []
    script = ["I've had stomach pain since yesterday.", "About 5.", "It comes and goes", "some nausea"]
    questions = []
    for i, text in enumerate(script, start=1):
        result = await llm.extract_turn(
            TurnContext(patient_state=state, recent_messages=history, user_message=text, turn=i, max_turns=8)
        )
        state, _ = state.merge(result.to_update())
        questions.append(result.output.next_question)
        history += [ChatTurn(role="user", content=text)]
        if result.output.next_question:
            history += [ChatTurn(role="assistant", content=result.output.next_question)]

    assert state.primary_symptoms == ["stomach pain"]
    assert state.symptom_duration == "since yesterday"
    assert state.symptom_severity == "5/10"
    assert state.symptom_frequency == "comes and goes"
    assert state.associated_symptoms == ["nausea"]
    assert questions[0] and "scale" in questions[0]
    assert questions[1] and "come and go" in questions[1]
    assert questions[-1] is None


async def test_mock_llm_flags_emergencies() -> None:
    result = await MockLLMProvider().extract_turn(
        CTX.model_copy(update={"user_message": "crushing chest pain going to my left arm"})
    )
    assert RedFlag.CHEST_PAIN_CARDIAC in result.output.red_flags
