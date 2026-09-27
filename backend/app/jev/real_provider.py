"""Real Jev provider backed by the official `typesafe-sdk` (AsyncTypeSafeClient).

This is the ONLY place a TypeSafe client is constructed, and it is only constructed when
JEV_PROVIDER=real. Nothing is created at import time.
"""

import time
from typing import Any

import httpx2
from typesafe_sdk import (
    AsyncTypeSafeClient,
    RetryPolicy,
    TypeSafeAPIResponseValidationError,
    TypeSafeAPITimeoutError,
    TypeSafeError,
    TypeSafeRateLimitError,
)

from app.jev.mapper import map_response
from app.jev.questions import build_questions, build_state
from app.jev.types import InvalidJevOutputError, JevCaseInput, JevDecision, JevUnavailableError


class RealJevDecisionProvider:
    name = "jev"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = AsyncTypeSafeClient(
            api_key=api_key,
            model=model,
            timeout=timeout_seconds,
            # One retry at most: cost-aware, and the SDK already honours Retry-After.
            retry=RetryPolicy(max_retries=1),
            transport=transport,
        )

    async def evaluate_case(self, case: JevCaseInput) -> JevDecision:
        questions = build_questions()
        state = build_state(case)
        raw_request: dict[str, Any] = {
            "state": state,
            "questions": {k: q.model_dump(mode="json", exclude_none=True) for k, q in questions.items()},
        }
        started = time.perf_counter()
        try:
            response = await self._client.system_one(state=state, questions=questions)
        except TypeSafeAPIResponseValidationError as exc:
            raise InvalidJevOutputError("response failed SDK validation") from exc
        except TypeSafeAPITimeoutError as exc:
            raise JevUnavailableError("timeout") from exc
        except TypeSafeRateLimitError as exc:
            raise JevUnavailableError("rate_limited") from exc
        except TypeSafeError as exc:
            raise JevUnavailableError(type(exc).__name__, retryable=False) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        try:
            request_id: str | None = response.request_id
        except TypeSafeError:
            request_id = None

        return map_response(
            response,
            provider=self.name,
            latency_ms=latency_ms,
            request_id=request_id,
            raw_request=raw_request,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
