# Healthcare Navigation Assistant — LLM + Jev

A conversational healthcare *navigation* assistant. A person describes their symptoms in plain language. An **LLM** runs the conversation and extracts structured facts. When enough is known, **Jev** (TypeSafe's typed decision model) makes **one** bounded, calibrated decision. The **backend** executes that decision through a deterministic safety policy and an explicit state machine. A developer **Decision Trace** and **OpenTelemetry** show exactly what happened, without spending another API call.

> ⚠️ This is a workflow prototype. It does **not** diagnose, prescribe or replace a clinician. Use synthetic data only.

```
User ─► LLM (1 call/turn: extract + red flags + next question) ─► Backend state
                                                                     │
                                                    enough info? ─── no ──► ask next question
                                                                     │ yes (or red flag / turn cap)
                                                                     ▼
                                     ONE Jev call: action · department · urgency · complexity
                                                   · needs_human_review · missing_info
                                                                     ▼
                              Deterministic safety policy (never downgrades urgency,
                              reconciles parallel answers, confidence-gated escalation)
                                                                     ▼
                              LLM explains the decision (template fallback) ─► User
```

| Layer | Responsibility |
|---|---|
| **LLM** (Groq, `openai/gpt-oss-120b`, strict JSON schema) | Understands the user, extracts facts, asks the next useful question, explains the result |
| **Jev** (`typesafe-sdk`, `AsyncTypeSafeClient.system_one`) | Makes the bounded decision with calibrated confidence |
| **Backend** (FastAPI, SQLAlchemy 2, Postgres) | Owns state, the state machine, safety policy, persistence and observability |
| **Frontend** (Next.js 16, TypeScript, Tailwind v4) | Landing, chat with progress ring and editable summary, recommendation card, developer Decision Trace |

## Why it's built this way

- **API-call budget.** A gathering turn makes 1 LLM call. The decision turn makes 1 LLM call, then **1 Jev call**, then 1 LLM call. A typical 5-message conversation is about **6 LLM calls and 1 Jev call**. Emergencies skip the explanation call entirely.
- **Safety doesn't depend on a model.**
  - Deterministic red-flag rules run on every message at no cost. An emergency still gets routed correctly **even if the LLM is down**.
  - Jev answers its questions in parallel, so a policy layer reconciles contradictory combinations. For example, `DERMATOLOGY` together with `EMERGENCY` becomes the emergency pathway.
  - The policy never lowers urgency.
  - Confidence below 0.6 escalates to a human.
- **Closed vocabulary.** Every model output is validated against Python enums. An unknown label is never executed, and the user gets "Automated decision unavailable" plus guidance to seek professional care.
- **Bounded workflow.** `COLLECTING_INFORMATION → READY_FOR_DECISION → JEV_PROCESSING → EXECUTING_ACTION → COMPLETED | ESCALATED | ERROR`. Illegal transitions raise. The `ASK_MORE_INFORMATION` loop runs at most once, and a hard cap of 8 turns forces a decision.
- **Privacy-aware telemetry.** Spans and logs carry IDs and enum values only, never patient text. A test enforces this.

## Quick start (mock mode: zero API calls)

Requirements: Python 3.13 with [uv](https://docs.astral.sh/uv/). Docker is optional, for Postgres and Jaeger.

```bash
cp .env.example backend/.env          # defaults: LLM_PROVIDER=mock, JEV_PROVIDER=mock
docker compose up -d                  # Postgres :5432, Jaeger UI http://localhost:16686
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:create_app --factory --reload --port 8000
```

API docs are at http://localhost:8000/docs.

No Docker? Use SQLite instead: `DATABASE_URL=sqlite+aiosqlite:///./dev.db` for both the `alembic` and `uvicorn` commands.

Then start the frontend in a second terminal:

```bash
cd frontend
pnpm install
pnpm dev                              # http://localhost:3100
```

Port 3100 is used so this project doesn't collide with other apps on 3000.

**Mock mode does not consume model API credits. Live mode consumes API credits and rate limit.**

### Real providers

```env
LLM_PROVIDER=groq
GROQ_API_KEY=...            # free tier at console.groq.com
JEV_PROVIDER=real
TYPESAFE_API_KEY=...
```

Each provider switches independently. For example, `LLM_PROVIDER=groq` with `JEV_PROVIDER=mock` gives real conversations while Jev access is pending. The Decision Trace always shows which provider made each decision.

When a real provider is enabled, the public-demo limits apply automatically: conversations per IP per hour, a daily conversation cap and a daily Jev-call cap.

### Fault injection (test the error UX without real APIs)

```env
MOCK_LLM_FAIL_MODE=rate_limit    # none | timeout | error | rate_limit | daily_quota | invalid | explain_error
MOCK_JEV_FAIL_MODE=timeout       # none | timeout | error | invalid
```

## Tests

```bash
cd backend
uv run pytest            # 76 tests: mock providers, SQLite in memory, outbound network BLOCKED
TEST_DATABASE_URL=postgresql+asyncpg://health:health@localhost:5432/health uv run pytest   # same suite on Postgres
uv run ruff check app tests && uv run mypy app
```

The tests assert the call budget through OpenTelemetry spans. Gathering turns must produce no `jev.evaluate` span, and a decision turn exactly one. Outbound network is blocked twice over: by pytest-socket, and by a guard on DNS resolution and on both SDKs' HTTP transports. A test proves that a mistakenly constructed real client still cannot reach the network.

CI runs the suite on SQLite **and** on a Postgres service, applies the Alembic migrations, and checks that they match the models.

Frontend:

```bash
cd frontend
pnpm typecheck && pnpm lint && pnpm build
pnpm test:e2e     # Playwright + axe on desktop and mobile; starts the backend in MOCK mode itself
```

The e2e suite drives real conversations through the UI: normal flow, emergency, refresh-resume and Decision Trace. It fails on any axe accessibility violation.

**Live smoke test. This consumes credits: 1 Jev call and 2 Groq requests.** It records the real Jev response for the offline tests:

```bash
uv run pytest -m live --force-enable-socket tests/live -s
```

## API

| Method | Path | Notes |
|---|---|---|
| POST | `/api/conversation/start` | Static greeting, no model call |
| POST | `/api/conversation/{id}/message` | `Idempotency-Key` header: a retried request never re-calls the models |
| GET | `/api/conversation/{id}` | Messages, state, progress, recommendation |
| GET / PATCH | `/api/conversation/{id}/state` | PATCH applies corrections, with at most one bounded re-evaluation |
| POST | `/api/conversation/{id}/decision/retry` | Only after a failed decision |
| GET | `/api/conversation/{id}/decisions` | Stored Jev decisions with probabilities |
| GET | `/api/conversation/{id}/trace` | Decision Trace built **only from stored data** |
| POST | `/api/conversation/{id}/reset` | New conversation; the old one is kept for audit |

Errors use one shape: `{"error": {"code", "message", "retryable", "request_id", "retry_after_seconds"}}`. Every response carries `X-Request-ID` and, when tracing is on, `X-Trace-ID`.

## Observability

Spans per turn: `conversation.request` → `llm.extract`, `state.update`, and on a decision turn also `jev.evaluate`, `workflow.execute` and `llm.response`. Attributes follow §27 of `claude.md` (`jev.action`, `jev.latency_ms`, `llm.model`, …). Traces are exported over OTLP to a local Jaeger, with no paid service involved. Logs are structured JSON and correlated by `request_id`.

## Before deploying the public demo

- Run uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy IPs>`. Otherwise every visitor shares the proxy's IP and one per-IP bucket.
- Set `DAILY_CONVERSATION_CAP` from your real Groq daily quota.
- Set a real `IP_HASH_SALT`.
- Set `CORS_ORIGINS` to the frontend URL.
- Add Cloudflare Turnstile on "Start conversation" (planned with the frontend).
- Keep keys only in the host's secret store. The frontend never sees them.

## Project layout

```
frontend/src/
  app/            routes: / (landing), /chat, /trace/[id]
  components/     chat, patient-summary, recommendation, progress, decision-trace, layout
  hooks/          use-conversation (resume, idempotent retries, corrections)
  lib/api/        typed client + schema.d.ts generated from backend/openapi.json
backend/app/
  domain/         enums (closed vocabulary), PatientState, state machine
  llm/            provider protocol, Groq + mock providers, prompts, templates
  jev/            provider protocol, real (typesafe-sdk) + mock providers, question set, mapper
  safety/         red-flag rules, post-Jev policy
  services/       conversation orchestrator, demo limits
  api/            routes + DTOs (OpenAPI → frontend types)
  db/             SQLAlchemy models; migrations/ holds Alembic
  observability/  OpenTelemetry + structlog
```
