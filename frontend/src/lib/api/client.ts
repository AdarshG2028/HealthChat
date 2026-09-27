/**
 * Typed API client. Every type comes from the backend's OpenAPI schema (`pnpm gen:api`),
 * so the Python enums are the single source of truth for the decision vocabulary.
 */
import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

type S = components["schemas"];
export type ConversationView = S["ConversationView"];
export type TurnResponse = S["TurnResponse"];
export type Message = S["MessageOut"];
export type PatientState = S["PatientState"];
export type PatientStateUpdate = S["PatientStateUpdate"];
export type Progress = S["Progress"];
export type Recommendation = S["Recommendation"];
export type DecisionTrace = S["DecisionTrace"];
export type Decision = S["DecisionOut"];
export type TraceEvent = S["TraceEvent"];
export type WorkflowState = S["WorkflowState"];
export type Urgency = S["Urgency"];

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const api = createClient<paths>({ baseUrl: API_URL });

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly retryable: boolean,
    public readonly status: number,
    public readonly retryAfterSeconds?: number | null,
  ) {
    super(message);
  }
}

function fail(status: number, body: unknown): never {
  const err = (body as { error?: S["ErrorBody"] } | undefined)?.error;
  if (err) throw new ApiError(err.code, err.message, err.retryable ?? false, status, err.retry_after_seconds);
  throw new ApiError("NETWORK_ERROR", "We couldn't reach the service. Check your connection and try again.", true, status);
}

async function run<T>(call: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  let result: Awaited<typeof call>;
  try {
    result = await call;
  } catch {
    fail(0, undefined);
  }
  if (result.data === undefined) fail(result.response.status, result.error);
  return result.data;
}

export const apiClient = {
  start: () => run(api.POST("/api/conversation/start")),

  get: (id: string) => run(api.GET("/api/conversation/{conversation_id}", { params: { path: { conversation_id: id } } })),

  /** The idempotency key makes a retried send safe: the backend never re-calls the models for it. */
  send: (id: string, content: string, idempotencyKey: string) =>
    run(
      api.POST("/api/conversation/{conversation_id}/message", {
        params: { path: { conversation_id: id }, header: { "idempotency-key": idempotencyKey } },
        body: { content },
      }),
    ),

  correct: (id: string, update: PatientStateUpdate) =>
    run(api.PATCH("/api/conversation/{conversation_id}/state", { params: { path: { conversation_id: id } }, body: update })),

  retryDecision: (id: string) =>
    run(api.POST("/api/conversation/{conversation_id}/decision/retry", { params: { path: { conversation_id: id } } })),

  reset: (id: string) => run(api.POST("/api/conversation/{conversation_id}/reset", { params: { path: { conversation_id: id } } })),

  trace: (id: string) => run(api.GET("/api/conversation/{conversation_id}/trace", { params: { path: { conversation_id: id } } })),
};
