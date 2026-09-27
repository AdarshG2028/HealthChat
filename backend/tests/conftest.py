"""Test harness: SQLite in memory, mock providers, in-memory OTel spans. Zero network, zero credits."""

import os
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db.models import Base
from app.jev.mock_provider import MockJevDecisionProvider
from app.llm.mock_provider import MockLLMProvider
from app.main import create_app

_EXPORTER = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(_EXPORTER))
trace.set_tracer_provider(_provider)


class NetworkBlockedError(RuntimeError):
    """Raised when a non-live test tries to reach a non-local host."""


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "test", "testserver"}


def _check_host(host: object) -> None:
    if host is not None and str(host) not in _LOCAL_HOSTS:
        raise NetworkBlockedError(f"Outbound network to {host!r} is blocked in tests (cost protection).")


@pytest.fixture(autouse=True)
def block_outbound_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Defence in depth on top of pytest-socket.

    pytest-socket's host allow-list patches `socket.connect`, which asyncio's Proactor loop on
    Windows bypasses (ConnectEx). So we also block at DNS resolution and at the real HTTP
    transports of both SDK stacks (httpx for Groq, httpx2 for TypeSafe). MockTransport and
    ASGITransport are separate classes and keep working.
    """
    if request.node.get_closest_marker("live"):
        return
    import socket

    import httpx2

    original_getaddrinfo = socket.getaddrinfo

    def guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        _check_host(host)
        return original_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)

    for module in (httpx, httpx2):
        for name, method in (("AsyncHTTPTransport", "handle_async_request"), ("HTTPTransport", "handle_request")):
            cls = getattr(module, name, None)
            if cls is None:
                continue
            original = getattr(cls, method)

            def guarded(self: Any, req: Any, _original: Any = original) -> Any:
                _check_host(req.url.host)
                return _original(self, req)

            monkeypatch.setattr(cls, method, guarded)


@pytest.fixture
def spans() -> InMemorySpanExporter:
    _EXPORTER.clear()
    return _EXPORTER


def span_names(exporter: InMemorySpanExporter) -> list[str]:
    return [s.name for s in exporter.get_finished_spans()]


def spans_named(exporter: InMemorySpanExporter, name: str) -> list[ReadableSpan]:
    return [s for s in exporter.get_finished_spans() if s.name == name]


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url="sqlite+aiosqlite://",
        otel_enabled=False,
        log_level="WARNING",
    )


@pytest.fixture
def llm() -> MockLLMProvider:
    return MockLLMProvider()


@pytest.fixture
def jev() -> MockJevDecisionProvider:
    return MockJevDecisionProvider()


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")  # e.g. Postgres in CI; SQLite in memory otherwise


@pytest.fixture
async def client(
    settings: Settings, llm: MockLLMProvider, jev: MockJevDecisionProvider
) -> AsyncIterator[httpx.AsyncClient]:
    if TEST_DATABASE_URL:
        engine = create_async_engine(TEST_DATABASE_URL)
    else:
        engine = create_async_engine(
            "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)  # clean slate per test
        await conn.run_sync(Base.metadata.create_all)
    app = create_app(settings, llm=llm, jev=jev, engine=engine)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


Chat = Callable[..., Any]


@pytest.fixture
def chat(client: httpx.AsyncClient) -> Chat:
    """Helper: start a conversation and send messages; returns the last JSON response."""

    async def _chat(*messages: str) -> tuple[str, dict[str, Any]]:
        start = await client.post("/api/conversation/start")
        assert start.status_code == 201, start.text
        cid = start.json()["id"]
        body: dict[str, Any] = start.json()
        for text in messages:
            resp = await client.post(f"/api/conversation/{cid}/message", json={"content": text})
            assert resp.status_code == 200, resp.text
            body = resp.json()
        return cid, body

    return _chat
