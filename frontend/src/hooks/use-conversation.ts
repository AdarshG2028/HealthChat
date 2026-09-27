"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  apiClient,
  type ConversationView,
  type Message,
  type PatientState,
  type PatientStateUpdate,
  type Progress,
  type Recommendation,
  type TurnResponse,
  type WorkflowState,
} from "@/lib/api/client";

const STORAGE_KEY = "carewise.conversationId";

export type ChatMessage = Message & {
  status?: "pending" | "failed";
  idempotencyKey?: string;
  error?: ApiError;
};

export type ConversationSnapshot = {
  id: string;
  status: WorkflowState;
  patientState: PatientState;
  progress: Progress;
  recommendation: Recommendation | null;
  emergency: boolean;
};

function storage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function snapshotOf(view: ConversationView | TurnResponse): ConversationSnapshot {
  return {
    id: "id" in view ? view.id : view.conversation_id,
    status: view.status,
    patientState: view.patient_state,
    progress: view.progress,
    recommendation: view.recommendation ?? null,
    emergency: view.emergency,
  };
}

export function useConversation() {
  const [snapshot, setSnapshot] = useState<ConversationSnapshot | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [fatal, setFatal] = useState<ApiError | null>(null);
  const started = useRef(false);

  const adopt = useCallback((view: ConversationView) => {
    setSnapshot(snapshotOf(view));
    setMessages(view.messages);
    storage()?.setItem(STORAGE_KEY, view.id);
  }, []);

  // Resume (GET: no model call) or start (static greeting: no model call).
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    (async () => {
      try {
        const saved = storage()?.getItem(STORAGE_KEY);
        if (saved) {
          try {
            adopt(await apiClient.get(saved));
            return;
          } catch (e) {
            if (!(e instanceof ApiError) || e.status !== 404) throw e;
          }
        }
        adopt(await apiClient.start());
      } catch (e) {
        setFatal(e instanceof ApiError ? e : new ApiError("UNKNOWN", "Something went wrong.", true, 0));
      }
    })();
  }, [adopt]);

  const deliver = useCallback(async (localId: string, content: string, key: string) => {
    if (!snapshot) return;
    setSending(true);
    setMessages((m) => m.map((x) => (x.id === localId ? { ...x, status: "pending", error: undefined } : x)));
    try {
      const turn = await apiClient.send(snapshot.id, content, key);
      setSnapshot(snapshotOf(turn));
      setMessages((m) => [
        ...m.map((x) => (x.id === localId ? { ...x, status: undefined } : x)),
        ...(m.some((x) => x.id === turn.message.id) ? [] : [turn.message]),
      ]);
    } catch (e) {
      const error = e instanceof ApiError ? e : new ApiError("UNKNOWN", "Something went wrong.", true, 0);
      setMessages((m) => m.map((x) => (x.id === localId ? { ...x, status: "failed", error } : x)));
    } finally {
      setSending(false);
    }
  }, [snapshot]);

  const send = useCallback(
    (content: string) => {
      const text = content.trim();
      if (!text || !snapshot || sending) return;
      const key = crypto.randomUUID();
      const local: ChatMessage = {
        id: `local-${key}`,
        role: "user",
        content: text,
        created_at: new Date().toISOString(),
        status: "pending",
        idempotencyKey: key,
      };
      setMessages((m) => [...m, local]);
      void deliver(local.id, text, key);
    },
    [snapshot, sending, deliver],
  );

  /** Retry with the SAME idempotency key: the backend replays instead of re-calling the LLM. */
  const retry = useCallback(
    (message: ChatMessage) => {
      if (message.idempotencyKey) void deliver(message.id, message.content, message.idempotencyKey);
    },
    [deliver],
  );

  const run = useCallback(async (action: () => Promise<ConversationView | TurnResponse>) => {
    setBusy(true);
    try {
      const result = await action();
      if ("messages" in result) adopt(result);
      else {
        setSnapshot(snapshotOf(result));
        setMessages((m) => [...m, result.message]);
      }
      return null;
    } catch (e) {
      return e instanceof ApiError ? e : new ApiError("UNKNOWN", "Something went wrong.", true, 0);
    } finally {
      setBusy(false);
    }
  }, [adopt]);

  const correct = useCallback(
    (update: PatientStateUpdate) => (snapshot ? run(() => apiClient.correct(snapshot.id, update)) : Promise.resolve(null)),
    [snapshot, run],
  );

  const retryDecision = useCallback(
    () => (snapshot ? run(() => apiClient.retryDecision(snapshot.id)) : Promise.resolve(null)),
    [snapshot, run],
  );

  const startOver = useCallback(
    () => (snapshot ? run(() => apiClient.reset(snapshot.id)) : Promise.resolve(null)),
    [snapshot, run],
  );

  return { snapshot, messages, sending, busy, fatal, send, retry, correct, retryDecision, startOver };
}
