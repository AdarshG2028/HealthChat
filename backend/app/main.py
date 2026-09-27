"""FastAPI application factory."""

import traceback
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.routes import router
from app.api.schemas import ErrorBody, ErrorResponse
from app.config import Settings, get_settings
from app.db.session import create_engine, create_sessionmaker
from app.domain.state_machine import IllegalTransitionError
from app.jev.types import JevDecisionProvider
from app.llm.types import LLMProvider
from app.observability.logging import log, setup_logging
from app.observability.telemetry import current_trace_id, setup_telemetry
from app.providers import build_jev_provider, build_llm_provider
from app.services.errors import ServiceError, UpstreamUnavailableError


def create_app(
    settings: Settings | None = None,
    *,
    llm: LLMProvider | None = None,
    jev: JevDecisionProvider | None = None,
    engine: AsyncEngine | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)
    engine = engine or create_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.sessionmaker = create_sessionmaker(engine)
        app.state.llm = llm or build_llm_provider(settings)
        app.state.jev = jev or build_jev_provider(settings)
        log.info(
            "app.started",
            llm_provider=app.state.llm.name,
            jev_provider=app.state.jev.name,
            real_providers=settings.uses_real_providers,
        )
        yield
        await app.state.llm.aclose()
        await app.state.jev.aclose()
        await engine.dispose()

    app = FastAPI(
        title="Healthcare Navigation Assistant API",
        version="0.1.0",
        description="LLM gathers information, Jev decides the pathway, the backend executes it.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Trace-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers["X-Request-ID"] = request_id
        if trace_id := current_trace_id():
            response.headers["X-Trace-ID"] = trace_id
        return response

    def _error(request: Request, status: int, body: ErrorBody) -> JSONResponse:
        body.request_id = getattr(request.state, "request_id", None)
        headers = {}
        if body.retry_after_seconds:
            headers["Retry-After"] = str(int(body.retry_after_seconds))
        return JSONResponse(ErrorResponse(error=body).model_dump(), status_code=status, headers=headers)

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError) -> JSONResponse:
        retry_after = exc.retry_after_seconds if isinstance(exc, UpstreamUnavailableError) else None
        return _error(
            request,
            exc.status_code,
            ErrorBody(code=exc.code, message=exc.message, retryable=exc.retryable, retry_after_seconds=retry_after),
        )

    @app.exception_handler(IllegalTransitionError)
    async def illegal_transition(request: Request, exc: IllegalTransitionError) -> JSONResponse:
        log.error("workflow.illegal_transition", current=exc.current, target=exc.target)
        return _error(
            request, 409, ErrorBody(code="ILLEGAL_TRANSITION", message="That action isn't possible right now.")
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _error(request, 422, ErrorBody(code="VALIDATION_ERROR", message="The request was not valid."))

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Frames only, never the exception message: messages (e.g. Pydantic's) can contain patient text (§55).
        frames = [f"{f.filename}:{f.lineno} in {f.name}" for f in traceback.extract_tb(exc.__traceback__)][-10:]
        log.error("unhandled_error", error_type=type(exc).__name__, frames=frames)
        return _error(
            request, 500, ErrorBody(code="INTERNAL_ERROR", message="Something went wrong on our side.", retryable=True)
        )

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)
    setup_telemetry(settings, app, engine)
    return app
