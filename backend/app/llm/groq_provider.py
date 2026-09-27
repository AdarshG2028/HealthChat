"""Groq LLM provider (free tier). The ONLY place a Groq client is constructed.

Gathering turns use strict `json_schema` structured output (one call returns extraction,
red flags, sufficiency and the next question). The decision explanation is plain text.
"""

import time
from typing import Any, cast

import groq
import httpx
from groq.types.chat import ChatCompletion
from pydantic import ValidationError

from app.llm.prompts import build_explanation_messages, build_turn_messages
from app.llm.types import (
    TURN_OUTPUT_SCHEMA,
    Explanation,
    ExplanationContext,
    LLMCallMeta,
    LLMInvalidOutputError,
    LLMRateLimitedError,
    LLMTurnOutput,
    LLMUnavailableError,
    TurnContext,
    TurnExtraction,
)


class GroqLLMProvider:
    name = "groq"

    def __init__(
        self, *, api_key: str, model: str, timeout_seconds: float, http_client: httpx.AsyncClient | None = None
    ) -> None:
        self.model = model
        # max_retries=0: the orchestrator decides what to do on failure (template / retry UI),
        # so the SDK must not silently multiply calls against the free-tier rate limit.
        self._client = groq.AsyncGroq(api_key=api_key, timeout=timeout_seconds, max_retries=0, http_client=http_client)

    async def extract_turn(self, ctx: TurnContext) -> TurnExtraction:
        started = time.perf_counter()
        completion = await self._call(
            messages=build_turn_messages(ctx),
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "turn_extraction", "strict": True, "schema": TURN_OUTPUT_SCHEMA},
            },
            max_completion_tokens=1024,
            temperature=0.2,
        )
        content = _complete_content(completion)
        try:
            output = LLMTurnOutput.model_validate_json(content)
        except ValidationError as exc:
            # Never log `exc` itself: Pydantic messages include input values (patient text).
            raise LLMInvalidOutputError("turn output failed schema validation") from exc
        return TurnExtraction(output=output, meta=self._meta(completion, started))

    async def explain_decision(self, ctx: ExplanationContext) -> Explanation:
        started = time.perf_counter()
        completion = await self._call(
            messages=build_explanation_messages(ctx),
            # gpt-oss is a reasoning model; hidden reasoning shares this budget.
            max_completion_tokens=800,
            temperature=0.4,
        )
        text = _complete_content(completion).strip()
        if len(text) < 20:
            raise LLMInvalidOutputError("explanation empty")
        return Explanation(text=text, meta=self._meta(completion, started))

    async def _call(
        self,
        messages: list[dict[str, str]],
        *,
        max_completion_tokens: int,
        temperature: float,
        response_format: dict[str, Any] | None = None,
    ) -> ChatCompletion:
        try:
            return await self._client.chat.completions.create(
                model=self.model,
                messages=cast(Any, messages),
                response_format=cast(Any, response_format),
                max_completion_tokens=max_completion_tokens,
                temperature=temperature,
                reasoning_effort="low",
                include_reasoning=False,
            )
        except groq.RateLimitError as exc:
            retry_after = exc.response.headers.get("retry-after")
            raise LLMRateLimitedError(float(retry_after) if retry_after else None) from exc
        except groq.APITimeoutError as exc:
            raise LLMUnavailableError("timeout") from exc
        except groq.APIConnectionError as exc:
            raise LLMUnavailableError("connection_error") from exc
        except groq.APIStatusError as exc:
            raise LLMUnavailableError(f"http_{exc.status_code}", retryable=exc.status_code >= 500) from exc

    def _meta(self, completion: ChatCompletion, started: float) -> LLMCallMeta:
        usage = completion.usage
        return LLMCallMeta(
            provider=self.name,
            model=completion.model or self.model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )

    async def aclose(self) -> None:
        await self._client.close()


def _complete_content(completion: ChatCompletion) -> str:
    """Return the content only if generation finished normally; truncated output is never shown."""
    choice = completion.choices[0]
    if choice.finish_reason != "stop":
        raise LLMInvalidOutputError(f"generation did not finish (finish_reason={choice.finish_reason})")
    return choice.message.content or ""
