# Healthcare AI Assistant — LLM + Jev

Build a polished, production-oriented healthcare conversational application using:

* Next.js
* TypeScript
* FastAPI
* PostgreSQL
* An LLM
* Jev / TypeSafe
* OpenTelemetry

The application should be designed as an **end-user healthcare workflow assistant**, not as a research benchmark.

---

# DECISIONS (2026-09-26) — THESE OVERRIDE ANY CONFLICTING TEXT BELOW

These were agreed after checking the live TypeSafe and Groq docs.

1. **Jev SDK:** use the official **Python** SDK `typesafe-sdk` (`from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul`) inside FastAPI. Do **not** use `@typesafe-ai/sdk` (TypeScript). Docs: https://docs.typesafe.ai/sdk/python.md (index: https://docs.typesafe.ai/llms.txt). Auth is `TYPESAFE_API_KEY`. The method is `client.system_one(state=..., questions={...})`.
2. **LLM:** **Groq free tier** (groq.com, Python SDK `groq`). Default model `openai/gpt-oss-120b` with strict `json_schema` structured output. Structured output does **not** support streaming on Groq, so only the plain-text explanation turn streams.
3. **API call budget:**
   - Gathering turn: **1 LLM call**, returning `{extracted_fields, red_flags, info_sufficient, next_question}` together.
   - Decision turn: 1 LLM call (extract), then **1 Jev call**, then 1 LLM call (explanation).
   - If the explanation call fails or is rate-limited, use a **deterministic template** built from the Jev decision.
   - A typical 5-message conversation costs about 6 LLM calls and 1 Jev call.
4. **Emergency short-circuit:** the LLM's `red_flags` output and deterministic backend rules both run on every turn at no extra call. Either one forces `READY_FOR_DECISION`. The static emergency banner must render even if both the LLM and Jev are down.
5. **One Jev call** asks these parallel questions:
   - `action` — Choice
   - `department` — Choice
   - `urgency` — Choice
   - `complexity` — Choice
   - `needs_human_review` — Noul
   - `missing_info` — Choice

   Jev answers the questions in parallel. A deterministic **safety policy** runs afterwards: it never downgrades urgency, fixes contradictory combinations, and a red flag means urgency is at least URGENT. **Confidence gating**: `action` or `department` confidence below 0.6, or `needs_human_review` at or above its threshold, means escalate.
6. **Enough-info guards:** a minimum core (primary symptom, duration, severity) plus a hard cap of **8 turns**, after which the decision is forced.
7. **Unified workflow states:** `COLLECTING_INFORMATION → READY_FOR_DECISION → JEV_PROCESSING → EXECUTING_ACTION → COMPLETED | ESCALATED | ERROR`. `ASK_MORE_INFORMATION` loops back to `COLLECTING_INFORMATION`. Illegal transitions raise an error.
8. **Extra endpoint:** `PATCH /api/conversation/{id}/state` for user corrections. At most one bounded Jev re-evaluation per correction.
9. **Store the full Jev request and response** (probabilities, confidence, model, request_id, usage) in JSONB for the Decision Trace.
10. **Provider env:** `LLM_PROVIDER=mock|groq`, `JEV_PROVIDER=mock|real`, `GROQ_API_KEY`, `TYPESAFE_API_KEY`. Real clients are constructed **only** inside the real providers.
11. **Tests:** pytest excludes the `live` marker by default, and an autouse fixture blocks the network. Mappers are tested against response fixtures recorded from a single manual live run.
12. **Frontend mocking:** no `NEXT_PUBLIC_DEMO_MODE` and no MSW. The frontend always talks to the real backend running with mock providers, including in Playwright e2e. TypeScript types are generated from `backend/openapi.json` (`pnpm gen:api`). CI fails if the contract drifts.
13. **Public demo with real APIs and hard limits:**
    - per-IP rate limit
    - 8-turn cap per conversation
    - global daily cap
    - Cloudflare Turnstile
    - on a 429, show a "demo busy" state and fall back to the template explanation
14. **Frontend design (2026-09-27):** based on the user's inspiration (soft powder-blue brand, off-white rounded cards, near-black pill buttons, pastel sage/taupe/lavender cards, Outfit font, tick-ring progress, "Your plan" hero card with a "Next action" card). All colours meet WCAG AA. Never invent social proof: no fake reviews, ratings, patient counts or doctors. The brand name "Carewise" is a placeholder, set in `frontend/src/lib/labels.ts` and the `Logo`.
15. **Dev ports:** API on 8000, frontend on **3100** (3000 is taken on the user's machine).
16. **Jev access is pending** (TypeSafe is invite-only). Run with `JEV_PROVIDER=mock` until a key exists. Only the Groq live tests have been run for real so far.

---

# 0. MOST IMPORTANT DEVELOPMENT RULES

## Product first

The immediate goal is to build a complete, polished, usable application.

Do NOT prioritize:

* Benchmarking
* Model comparisons
* Research experiments
* Accuracy studies
* Large evaluation datasets
* A/B testing
* Cost benchmarking

Those can be added later if API credits remain.

The current goal is:

> Build the best possible end-user experience and demonstrate a clean LLM + Jev architecture.

---

# 1. API COST IS A HARD CONSTRAINT

The LLM and Jev APIs may consume paid credits.

Treat API calls as a limited resource.

## NEVER waste API calls on:

* frontend testing
* UI testing
* unit tests
* repeated manual tests
* automated test suites
* rendering components
* page refreshes
* development hot reloads
* repeated identical requests
* benchmarking
* unnecessary retries

The application must be designed so that most development can happen using mocks.

---

# 2. MOCK-FIRST DEVELOPMENT

Create interfaces around both the LLM and Jev.

For example:

```text
LLMProvider
├── RealLLMProvider
└── MockLLMProvider

JevDecisionProvider
├── RealJevDecisionProvider
└── MockJevDecisionProvider
```

The application should be able to run completely without paid APIs.

Development mode should use mocks unless explicitly configured otherwise.

For example:

```env
LLM_PROVIDER=mock
JEV_PROVIDER=mock
```

Production:

```env
LLM_PROVIDER=groq
JEV_PROVIDER=real
```

Do not hardcode provider selection throughout the application.

---

# 3. LIVE API TESTING MUST BE EXPLICIT

Never make real API calls automatically from:

```bash
npm test
pytest
```

or normal application development.

Create explicit commands for live testing.

For example:

```bash
npm run test:live
```

or:

```bash
python -m pytest tests/live
```

The exact commands can depend on the implementation.

Document clearly:

> Live tests consume API credits.

---

# 4. PRODUCT CONCEPT

Build a healthcare conversational assistant that helps users determine an appropriate **next healthcare pathway** based on the information they provide.

Example:

User:

> I've been having stomach pain since yesterday.

The assistant naturally asks relevant questions.

For example:

> Is the pain constant, or does it come and go?

The user responds.

The assistant continues until enough relevant information has been gathered.

The user should NOT be presented with a giant medical form.

The experience should feel like a natural conversation.

---

# 5. CORE ARCHITECTURE

The architecture is:

```text
                    USER
                     │
                     ▼
              ┌──────────────┐
              │     LLM      │
              │ Conversation │
              │ + Extraction │
              └──────┬───────┘
                     │
                     ▼
              ┌──────────────┐
              │ Backend State│
              └──────┬───────┘
                     │
             Enough information?
                /           \
              NO             YES
              │               │
              ▼               ▼
             LLM             JEV
        asks question      decision
              │               │
              │               ▼
              │         Workflow action
              │               │
              │               ▼
              │              LLM
              │               │
              └──────────────►│
                              ▼
                             USER
```

Responsibilities:

### LLM

The LLM is responsible for:

* Understanding natural language
* Conversation
* Extracting structured information
* Identifying relevant missing information
* Asking follow-up questions
* Explaining decisions to the user

### Jev

Jev is responsible for:

* Bounded workflow decisions
* Choosing the next workflow action
* Routing
* Urgency classification
* Complexity classification
* Human-review recommendation

### Backend

Backend is responsible for:

* State
* Workflow orchestration
* Validation
* Calling models
* Executing Jev decisions
* Persistence
* Error handling
* Observability

### Frontend

Frontend is responsible for:

* Excellent UX
* Conversation
* Progress
* Patient information summary
* Final recommendation
* Decision trace for developers

---

# 6. DO NOT CALL JEV ON EVERY MESSAGE

This is critical.

Do NOT implement:

```text
User
→ LLM
→ Jev
→ LLM
→ User
```

for every message.

That would unnecessarily increase cost and latency.

Instead:

```text
User
 ↓
LLM
 ↓
Update state
 ↓
Enough information?
 ├── NO
 │    ↓
 │   LLM asks question
 │    ↓
 │   User
 │
 └── YES
      ↓
     ONE JEV CALL
      ↓
     Workflow decision
      ↓
     LLM communicates result
      ↓
     User
```

Jev should only be called when a meaningful decision is required.

---

# 7. LLM INFORMATION GATHERING

The LLM should gradually construct a structured patient state.

Example:

```json
{
  "age": null,
  "sex": null,
  "primary_symptoms": [],
  "symptom_duration": null,
  "symptom_severity": null,
  "symptom_frequency": null,
  "associated_symptoms": [],
  "existing_conditions": [],
  "current_medications": [],
  "known_allergies": [],
  "relevant_medical_history": [],
  "additional_information": []
}
```

These are not necessarily required fields for every case.

The LLM should ask only questions relevant to the user's situation.

For example, a user reporting a skin rash should not necessarily be asked every question that would be relevant to chest pain.

---

# 8. LLM SYSTEM PROMPT BEHAVIOR

The LLM should behave as a conversational information-gathering assistant.

It should:

1. Understand the user's message.
2. Extract relevant information.
3. Update the structured state.
4. Identify important missing information.
5. Ask the next useful question.
6. Avoid unnecessary questions.
7. Avoid diagnosis.
8. Avoid prescriptions.
9. Avoid independently deciding the final healthcare pathway.
10. Signal when enough information has been collected.

The LLM should NOT independently determine:

* final department
* final urgency
* human escalation
* final workflow action

Those decisions belong to Jev/backend logic.

---

# 9. STATE MANAGEMENT

Maintain the canonical state on the backend.

Never rely exclusively on the LLM's conversational memory.

Store:

* conversation ID
* messages
* structured patient state
* workflow status
* Jev decisions
* timestamps
* provider information
* errors

The backend should know whether the application is currently:

```text
COLLECTING_INFORMATION
READY_FOR_DECISION
JEV_PROCESSING
EXECUTING_ACTION
COMPLETED
ESCALATED
ERROR
```

(Unified names; see DECISIONS #7. §52/§53 use the same names.)

---

# 10. ADAPTIVE INFORMATION COLLECTION

The assistant should not simply check:

```text
if age == null:
    ask age
if sex == null:
    ask sex
if symptoms == null:
    ask symptoms
```

Instead, make information collection context-aware.

For example:

```text
User reports headache
        ↓
LLM determines relevant information
        ↓
Duration?
Severity?
Frequency?
Associated symptoms?
Relevant history?
        ↓
Enough information?
```

The system should avoid turning the conversation into a form.

---

# 11. JEV DECISION LAYER

Once enough information has been collected, send the structured case to Jev.

Possible actions:

```text
ASK_MORE_INFORMATION
PROVIDE_GENERAL_GUIDANCE
REFER_TO_DOCTOR
ROUTE_TO_DEPARTMENT
ESCALATE_TO_HUMAN
END
```

Possible departments:

```text
GENERAL_MEDICINE
CARDIOLOGY
NEUROLOGY
PULMONOLOGY
GASTROENTEROLOGY
ORTHOPEDICS
DERMATOLOGY
ENT
GYNECOLOGY
UROLOGY
EMERGENCY
OTHER
```

Urgency:

```text
ROUTINE
URGENT
EMERGENCY
```

Complexity:

```text
SIMPLE
MODERATE
COMPLEX
```

Human review:

```text
probability / confidence
```

---

# 12. ONE JEV REQUEST FOR RELATED DECISIONS

Do not make separate Jev API calls for:

* action
* department
* urgency
* complexity
* human review

if these can be obtained within one Jev decision request.

Conceptually:

```text
Jev
 ├── action
 ├── department
 ├── urgency
 ├── complexity
 └── human_review
```

Follow the current official Jev SDK syntax.

Do NOT invent an API based on this conceptual structure.

---

# 13. OFFICIAL TYPESAFE SDK

Jev is a newly released technology.

Do NOT assume the SDK syntax from training knowledge.

Before implementing Jev, inspect the current official documentation.

Use the official **Python** package (the backend is FastAPI; see DECISIONS #1):

```text
typesafe-sdk        (import: typesafe_sdk; async client: AsyncTypeSafeClient)
```

Install it using the current official instructions.

Current official Python documentation:

```text
https://docs.typesafe.ai/sdk/python.md
https://www.typesafeai.org/guides/jev-python
```

The official SDK documentation is the source of truth.

Do not invent:

* package names
* method names
* endpoint URLs
* authentication format
* request schemas
* response schemas

If the current SDK differs from this specification, follow the current official documentation.

The Jev integration must be strongly typed.

---

# 14. JEV PROVIDER ABSTRACTION

Create:

```text
JevDecisionProvider
```

with:

```text
RealJevDecisionProvider
MockJevDecisionProvider
```

Conceptually:

```typescript
interface JevDecisionProvider {
  evaluateCase(input: JevCaseInput): Promise<JevDecision>;
}
```

The actual implementation should follow the official SDK.

The rest of the application must not care whether Jev is real or mocked.

---

# 15. TYPE-SAFE DECISION VOCABULARY

Define central types for:

```text
WorkflowAction
Department
Urgency
Complexity
HumanReview
JevDecision
```

Do not allow arbitrary strings from external model output to flow through the application.

Validate model responses before executing them.

---

# 16. MOCK JEV

The mock Jev provider should support realistic scenarios.

Example:

```text
ROUTE_TO_DEPARTMENT
GASTROENTEROLOGY
ROUTINE
MODERATE
```

Another:

```text
REFER_TO_DOCTOR
GENERAL_MEDICINE
URGENT
MODERATE
```

Another:

```text
ESCALATE_TO_HUMAN
OTHER
URGENT
COMPLEX
```

Another:

```text
PROVIDE_GENERAL_GUIDANCE
GENERAL_MEDICINE
ROUTINE
SIMPLE
```

Use deterministic mock responses.

Do not randomly generate decisions because deterministic behavior makes development easier.

---

# 17. MOCK LLM

Create a mock LLM provider as well.

It should allow frontend/backend development without API usage.

Example mock conversation:

```text
User:
I've had stomach pain since yesterday.

Assistant:
How severe is the pain on a scale from 1 to 10?

User:
About 5.

Assistant:
Is the pain constant or does it come and go?
```

The mock system should be sufficient for:

* frontend development
* loading states
* conversation UI
* error states
* decision trace
* workflow testing

---

# 18. HEALTHCARE SAFETY

This is a healthcare workflow prototype.

Do NOT claim that the system:

* diagnoses disease
* replaces doctors
* prescribes medication
* provides definitive medical treatment

The assistant should provide general educational information and healthcare pathway recommendations.

For potentially serious situations, the application should encourage appropriate professional or emergency care.

Do not present a model decision as a definitive medical diagnosis.

Use synthetic/de-identified information during development.

---

# 19. USER EXPERIENCE

The UI should feel like a modern consumer healthcare application.

Not:

* an admin dashboard
* a developer tool
* a research interface
* a medical form

The main experience should be:

```text
Welcome
 ↓
Conversation
 ↓
Information gathering
 ↓
Reviewing information
 ↓
Recommendation
 ↓
Next step
```

---

# 20. CONVERSATION UI

Build a polished chat interface.

It should include:

* user messages
* assistant messages
* typing/loading state
* error state
* retry
* conversation history
* progress indicator
* structured information summary

Do not expose model implementation details in the normal chat.

---

# 21. INFORMATION SUMMARY

Before or after the decision, show the user a concise summary.

Example:

```text
What we understood

Symptoms
Stomach pain

Duration
Since yesterday

Severity
Moderate

Associated symptoms
Nausea

Medical history
No relevant history provided
```

Allow the user to correct information where practical.

If the user corrects something important, update the backend state.

---

# 22. FINAL RECOMMENDATION CARD

Example:

```text
Recommended next step

General Medicine

Urgency
Routine

Case complexity
Moderate

What to do next

Consider scheduling a consultation with a general physician.

Why this was recommended

Based on the information you provided...
```

Keep the output concise.

Do not show raw model probabilities to normal users unless there is a clear UX reason.

---

# 23. JEV DECISION TRACE

Implement this as a real feature.

This should NOT require another API call.

The decision trace should use data already produced during the workflow.

Create a developer/admin panel that displays:

```text
Jev Decision Trace

Conversation ID
abc123

Decision status
Completed

Information available
...

Action
ROUTE_TO_DEPARTMENT

Department
GASTROENTEROLOGY

Urgency
ROUTINE

Complexity
MODERATE

Human review probability
0.18

Decision timestamp
...

Jev model/version
...

Provider
Jev
```

Also show:

```text
Workflow

COLLECTING_INFORMATION
        ↓
READY_FOR_DECISION
        ↓
JEV_DECISION
        ↓
ROUTE_TO_DEPARTMENT
        ↓
COMPLETED
```

This makes the role of Jev visible without exposing internal reasoning.

---

# 24. DO NOT SHOW CHAIN-OF-THOUGHT

The decision trace must NOT contain hidden reasoning or chain-of-thought.

Show:

* structured inputs
* decision outputs
* probabilities/confidence
* workflow transitions
* timestamps
* model/provider metadata

Do not show private internal reasoning.

---

# 25. OBSERVABILITY

Implement OpenTelemetry from the beginning.

This is important.

OpenTelemetry itself should be used for instrumentation and local observability without introducing unnecessary paid infrastructure.

Track:

```text
HTTP request
   ↓
Conversation service
   ↓
LLM call
   ↓
State update
   ↓
Jev call
   ↓
Workflow execution
```

---

# 26. OPENTELEMETRY TRACES

Create meaningful spans.

Example:

```text
conversation.request
 ├── llm.extract
 ├── state.update
 ├── jev.evaluate
 └── workflow.execute
```

For a normal information-gathering turn:

```text
conversation.request
 ├── llm.extract
 └── state.update
```

For a final decision:

```text
conversation.request
 ├── llm.extract
 ├── state.update
 ├── jev.evaluate
 ├── workflow.execute
 └── llm.response
```

This should make it immediately visible when Jev is called.

---

# 27. OPENTELEMETRY ATTRIBUTES

Useful span attributes:

```text
conversation.id
request.id
workflow.state
llm.provider
llm.model
llm.latency_ms
jev.provider
jev.model
jev.latency_ms
jev.action
jev.department
jev.urgency
jev.complexity
workflow.action
error.type
```

Be careful with healthcare data.

Do NOT put sensitive patient information or raw medical messages into telemetry attributes.

Use IDs rather than personally identifiable or sensitive medical data.

---

# 28. CORRELATION

Use a request/conversation ID throughout the system.

Example:

```text
conversation_id
request_id
trace_id
```

A developer should be able to take a conversation ID and understand:

```text
Conversation
    ↓
LLM call
    ↓
State update
    ↓
Jev call
    ↓
Decision
    ↓
Workflow
```

---

# 29. LOCAL OBSERVABILITY

Prefer a local/developer-friendly setup initially.

For example:

```text
Application
    ↓
OpenTelemetry SDK
    ↓
OTLP
    ↓
Local collector
    ↓
Jaeger / compatible local backend
```

The exact stack can be selected based on current ecosystem compatibility.

The important requirement is:

> Do not introduce a paid observability service just for this project.

Make observability runnable locally.

---

# 30. STRUCTURED LOGGING

Add structured logs.

Example:

```json
{
  "event": "jev.decision.completed",
  "conversation_id": "...",
  "request_id": "...",
  "action": "ROUTE_TO_DEPARTMENT",
  "department": "GASTROENTEROLOGY",
  "urgency": "ROUTINE",
  "complexity": "MODERATE"
}
```

Do not log sensitive patient information.

---

# 31. DATABASE

Use PostgreSQL.

Suggested entities:

### Conversation

```text
id
status
created_at
updated_at
```

### Message

```text
id
conversation_id
role
content
created_at
```

### PatientState

```text
conversation_id
state JSONB
updated_at
```

### JevDecision

```text
id
conversation_id
action
department
urgency
complexity
human_review_probability
provider
model_version
created_at
```

### WorkflowEvent

```text
id
conversation_id
event_type
metadata JSONB
created_at
```

Do not over-engineer the schema.

---

# 32. WORKFLOW EVENTS

Store important workflow transitions.

For example:

```text
CONVERSATION_STARTED

MESSAGE_RECEIVED

PATIENT_STATE_UPDATED

INFORMATION_COLLECTION_CONTINUED

READY_FOR_JEV

JEV_DECISION_COMPLETED

ACTION_EXECUTED

HUMAN_REVIEW_REQUIRED

CONVERSATION_COMPLETED
```

This allows the Decision Trace to reconstruct the workflow without making additional model calls.

---

# 33. API ENDPOINTS

Implement:

```text
POST /api/conversation/start

POST /api/conversation/{id}/message

GET /api/conversation/{id}

GET /api/conversation/{id}/state

GET /api/conversation/{id}/decisions

GET /api/conversation/{id}/trace

PATCH /api/conversation/{id}/state      (user corrections; see DECISIONS #8)

POST /api/conversation/{id}/reset
```

The trace endpoint should return the stored workflow/decision information.

It must NOT call Jev again.

---

# 34. MESSAGE FLOW

The message endpoint should roughly perform:

```text
1. Receive user message

2. Store message

3. Start OpenTelemetry span

4. Call LLM

5. Extract structured information

6. Update patient state

7. Store workflow event

8. Determine whether enough information exists

9. If incomplete:
       ask LLM for next question
       return response

10. If complete:
       call Jev once

11. Store Jev decision

12. Store workflow event

13. Execute backend workflow

14. If user-facing explanation is required:
       call LLM

15. Store response

16. Return response
```

Avoid unnecessary calls.

---

# 35. IMPORTANT: JEV SHOULD NOT GENERATE USER TEXT

Jev is the decision layer.

The LLM should communicate the decision naturally to the user.

For example:

```text
Jev:

ROUTE_TO_DEPARTMENT
GASTROENTEROLOGY
ROUTINE
MODERATE
```

Then:

```text
LLM:

"Based on the information you've shared, it would be reasonable to speak with a gastroenterology specialist..."
```

The LLM communicates.

Jev decides.

---

# 36. IF JEV REQUESTS MORE INFORMATION

If Jev returns:

```text
ASK_MORE_INFORMATION
```

do not ask the user directly using Jev.

Instead:

```text
Jev
 ↓
Backend identifies requested information
 ↓
LLM
 ↓
Natural question
 ↓
User
```

Then update state and continue.

Do not call Jev again until the new information has been collected.

---

# 37. IF JEV RECOMMENDS HUMAN REVIEW

Stop autonomous workflow where appropriate.

Show something like:

```text
Additional review recommended

Your information should be reviewed by a healthcare professional.

Please consult an appropriate medical professional.
```

Do not pretend that a human has actually reviewed the case unless a real human workflow exists.

---

# 38. ERROR HANDLING

Handle:

* LLM timeout
* LLM API failure
* Jev timeout
* Jev API failure
* invalid Jev output
* database failure
* malformed state
* network errors

Never silently fabricate a model response.

If Jev fails:

```text
Automated decision unavailable
```

and provide a safe fallback directing the user toward appropriate professional care.

---

# 39. JEV FAILURE MUST NOT CRASH THE SYSTEM

Because Jev is behind:

```text
JevDecisionProvider
```

the rest of the system should remain operational.

Use:

```text
RealJevDecisionProvider
MockJevDecisionProvider
```

The workflow should handle provider failure gracefully.

---

# 40. FRONTEND ARCHITECTURE

Use:

```text
Next.js
TypeScript
```

Keep components separated.

Suggested:

```text
components/
  chat/
  patient-summary/
  recommendation/
  progress/
  decision-trace/
  workflow/
  layout/
```

Potential screens:

```text
Landing
Chat
Assessment
Recommendation
Decision Trace
```

---

# 41. FRONTEND SHOULD BE MOCKABLE

The frontend should work without backend model calls.

Superseded by DECISIONS #12: there is no `NEXT_PUBLIC_DEMO_MODE`. The frontend talks to the backend running with mock providers. For frontend-only work, MSW handlers serve the same predefined conversations and Jev decisions.

This allows UI development without spending API credits.

---

# 42. RESPONSIVE DESIGN

The application must work well on:

* Desktop
* Tablet
* Mobile

The chat interface should be particularly polished on mobile.

---

# 43. ACCESSIBILITY

Implement:

* semantic HTML
* keyboard navigation
* accessible buttons
* readable contrast
* screen-reader-friendly labels
* loading announcements where appropriate

---

# 44. SECURITY

Do not expose:

```text
TYPESAFE_API_KEY
LLM_API_KEY
DATABASE_URL
```

to the frontend.

All model calls happen server-side.

Use environment variables.

Provide:

```text
.env.example
```

and ensure secrets are excluded from Git.

---

# 45. BACKEND STRUCTURE

Suggested:

```text
backend/
  app/
    main.py
    config.py

    api/
      routes.py

    models/
      conversation.py
      message.py
      patient_state.py
      decision.py
      workflow_event.py

    llm/
      client.py
      provider.py
      real_provider.py
      mock_provider.py
      prompts.py
      extractor.py

    jev/
      client.py
      provider.py
      real_provider.py
      mock_provider.py
      decisions.py

    agent/
      controller.py
      state.py
      actions.py

    services/
      conversation.py
      patient_state.py
      workflow.py

    observability/
      telemetry.py
      logging.py

    db/
      database.py

    tests/
```

Adapt this if a cleaner architecture is appropriate.

---

# 46. TESTING

Tests should primarily be local and deterministic.

Test:

### State

* state updates
* merging information
* corrections

### Conversation

* information gathering
* follow-up questions
* completed state

### Jev

* mock Jev decisions
* decision validation
* action mapping

### Workflow

* routing
* referral
* escalation
* guidance
* completion

### Errors

* LLM failure
* Jev failure
* database failure
* invalid responses

### Observability

* spans created
* workflow events recorded
* request IDs propagated

Tests must NOT consume paid API credits.

---

# 47. LIVE API TESTS

Keep live API tests separate.

They should be manually triggered.

Never execute them automatically on:

```text
git commit
npm test
pytest
frontend build
frontend startup
backend startup
```

---

# 48. NO BENCHMARKING NOW

Explicitly DO NOT implement:

```text
LLM-only baseline
Jev-only baseline
LLM vs Jev benchmark
accuracy benchmark
latency benchmark
cost benchmark
evaluation dataset
A/B testing
model leaderboard
statistical evaluation
```

This is intentionally deferred.

If there are API credits remaining after the application is complete, benchmarking can be added later.

---

# 49. WHAT WE DO WANT NOW

We DO want:

```text
Production-like architecture
Clean UX
Strong typing
LLM/Jev separation
Mock providers
Real providers
Jev decision trace
Workflow trace
OpenTelemetry
Structured logging
Error handling
Database persistence
Responsive frontend
Accessibility
Security
Unit tests
Integration tests using mocks
```

These are part of the product and engineering quality.

---

# 50. OBSERVABILITY ≠ BENCHMARKING

Do not confuse the two.

OpenTelemetry is required.

It is useful for:

* debugging
* tracing
* latency visibility
* identifying unnecessary calls
* understanding workflow
* diagnosing failures

It does NOT mean building a research benchmark.

Implement observability without creating a paid analytics infrastructure.

---

# 51. COST-AWARE DEVELOPMENT

Whenever implementing a feature, ask:

> Can this be implemented without a real model/API call?

If yes, use mocks.

For example:

### UI loading state

Use mock data.

### Recommendation card

Use mock Jev decision.

### Decision Trace

Use stored/mock decision.

### OpenTelemetry

Use local instrumentation.

### Error states

Inject mock errors.

### Conversation flow

Use mock LLM.

### Jev workflow

Use mock Jev.

Only use real APIs when verifying the actual integration.

---

# 52. DO NOT CREATE AUTOMATIC API LOOPS

Avoid architectures where:

```text
LLM calls Jev
Jev calls LLM
LLM calls Jev
Jev calls LLM
...
```

The workflow should have explicit state transitions.

Prefer:

```text
COLLECTING_INFORMATION

↓

READY_FOR_DECISION

↓

JEV_DECISION

↓

EXECUTE_ACTION

↓

COMPLETED
```

If additional information is requested:

```text
JEV_DECISION
↓
ASK_MORE_INFORMATION
↓
COLLECTING_INFORMATION
↓
READY_FOR_DECISION
↓
JEV_DECISION
```

This is explicit and bounded.

---

# 53. CONVERSATION STATE MACHINE

Implement an explicit workflow state machine.

For example:

```text
START
 ↓
COLLECTING_INFORMATION
 ↓
READY_FOR_DECISION
 ↓
JEV_PROCESSING
 ↓
ACTION_REQUIRED
 ├── ASK_MORE_INFORMATION
 │       ↓
 │   COLLECTING_INFORMATION
 │
 ├── ROUTE_TO_DEPARTMENT
 │       ↓
 │    COMPLETED
 │
 ├── REFER_TO_DOCTOR
 │       ↓
 │    COMPLETED
 │
 ├── PROVIDE_GENERAL_GUIDANCE
 │       ↓
 │    COMPLETED
 │
 ├── ESCALATE_TO_HUMAN
 │       ↓
 │    ESCALATED
 │
 └── END
        ↓
     COMPLETED
```

This state machine should be visible in the developer Decision Trace.

---

# 54. DECISION TRACE EXAMPLE

A developer should be able to see:

```text
Conversation #8F92

Timeline

12:31:02
MESSAGE_RECEIVED

12:31:03
LLM_EXTRACTION

12:31:03
PATIENT_STATE_UPDATED

12:31:20
MESSAGE_RECEIVED

12:31:21
LLM_EXTRACTION

12:31:21
PATIENT_STATE_UPDATED

12:31:22
READY_FOR_JEV

12:31:23
JEV_DECISION_COMPLETED

Action:
ROUTE_TO_DEPARTMENT

Department:
GASTROENTEROLOGY

Urgency:
ROUTINE

Complexity:
MODERATE

Human review:
0.18

12:31:23
WORKFLOW_ACTION_EXECUTED

12:31:24
LLM_RESPONSE_GENERATED

12:31:24
CONVERSATION_COMPLETED
```

This should come from stored events/traces.

Do NOT make additional model calls just to generate the trace.

---

# 55. NO SENSITIVE TELEMETRY

Healthcare information can be sensitive.

Do not put:

* patient names
* phone numbers
* email addresses
* medical messages
* diagnoses
* medications
* medical history

into OpenTelemetry span attributes or logs unless absolutely necessary and explicitly designed for secure handling.

Prefer:

```text
conversation_id
request_id
trace_id
```

and aggregate metadata.

---

# 56. DOCUMENTATION

Create:

```text
README.md
```

Include:

* project overview
* architecture
* setup
* environment variables
* local development
* mock mode
* real provider mode
* testing
* OpenTelemetry setup
* Jev integration
* API documentation
* safety limitations

Clearly state:

```text
Mock mode does not consume model API credits.
Live mode consumes API credits.
```

---

# 57. ENVIRONMENT CONFIGURATION

Example:

```text
DATABASE_URL=

LLM_PROVIDER=mock          # mock | groq
GROQ_API_KEY=
LLM_MODEL=openai/gpt-oss-120b

JEV_PROVIDER=mock          # mock | real
TYPESAFE_API_KEY=

OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=
```

Do not assume exact TypeSafe environment variable names if the official SDK specifies another mechanism.

Follow the current official SDK documentation.

---

# 58. DEVELOPMENT COMMANDS

Provide clear commands for:

```text
frontend development
backend development
database setup
tests
mock mode
live integration testing
OpenTelemetry/local observability
```

Make sure normal development uses mocks.

---

# 59. FINAL ARCHITECTURAL PRINCIPLE

The application should clearly demonstrate:

```text
LLM
=
Understands the user

Jev
=
Decides what the system should do

Backend
=
Executes the decision

OpenTelemetry
=
Shows what happened

Decision Trace
=
Makes the workflow understandable to developers

Frontend
=
Makes everything simple for the user
```

The user should never need to understand Jev to use the application.

---

# 60. IMPLEMENTATION PRIORITY

Implement in this exact priority:

## Priority 1

Working application foundation.

## Priority 2

Natural conversational information gathering.

## Priority 3

Structured backend state.

## Priority 4

Jev integration using the official TypeSafe SDK.

## Priority 5

Bounded workflow state machine.

## Priority 6

Excellent end-user UX.

## Priority 7

Mock providers and cost protection.

## Priority 8

Jev Decision Trace.

## Priority 9

OpenTelemetry and structured observability.

## Priority 10

Testing and error handling.

## Priority 11

Polish and responsiveness.

Do NOT move to benchmarking after this automatically.

Stop once the product is complete.

---

# 61. FUTURE PHASE — DO NOT IMPLEMENT NOW

Later, if API credits remain, we may add:

```text
Benchmarking
LLM-only comparison
Jev-assisted comparison
Latency analysis
Cost analysis
Decision consistency
Evaluation datasets
```

But this is intentionally excluded from the current implementation.

---

# 62. IMPORTANT FINAL INSTRUCTION TO CLAUDE

Do not blindly implement this specification from memory.

Before implementing Jev:

1. Search/read the current official TypeSafe Jev documentation.
2. Verify the current Python SDK (`typesafe-sdk`).
3. Verify the current API.
4. Verify authentication.
5. Verify the current decision primitives.
6. Verify the current request/response types.
7. Use the official SDK as the source of truth.

Official documentation:

https://docs.typesafe.ai/sdk/python.md

Use:

```text
typesafe-sdk   (Python, AsyncTypeSafeClient)
```

where appropriate according to the current official documentation.

If something in this specification conflicts with the current official SDK, adapt the implementation to the official SDK while preserving the architectural intent.

---

# FINAL GOAL

At the end of this implementation, I should have a polished healthcare AI application where:

```text
User
  ↓
Natural conversation
  ↓
LLM gathers relevant information
  ↓
Backend maintains structured state
  ↓
Enough information?
  ↓
Jev makes the bounded decision
  ↓
Backend executes it
  ↓
LLM communicates the result
  ↓
User sees a clear next step
```

And as a developer I should be able to see:

```text
Conversation
     ↓
LLM
     ↓
State
     ↓
Jev
     ↓
Decision
     ↓
Workflow
```

through the **Jev Decision Trace + OpenTelemetry**, without spending additional API credits.

The application should be:

* user-friendly
* production-oriented
* type-safe
* observable
* testable
* cost-conscious
* modular
* maintainable

Build the product first.

Benchmark later.
