"use client";

import { ChevronDown, Code2, RotateCw, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";

import { Composer } from "@/components/chat/composer";
import { EmergencyBanner } from "@/components/chat/emergency-banner";
import { MessageBubble, TypingIndicator } from "@/components/chat/message-bubble";
import { SummaryCard } from "@/components/patient-summary/summary-card";
import { ProgressRing } from "@/components/progress/progress-ring";
import { RecommendationCard } from "@/components/recommendation/recommendation-card";
import { Button, Card } from "@/components/ui";
import { type ConversationSnapshot, useConversation } from "@/hooks/use-conversation";

const TOPIC_STARTERS: Record<string, string> = {
  stomach: "I've had stomach pain since ",
  headache: "I've been getting headaches ",
  skin: "I have a rash on my ",
  breathing: "I've had a cough for ",
};

/** Share of the check that is done: the 3 core facts dominate, extras add a little. */
function completion(s: ConversationSnapshot): number {
  if (s.status === "COMPLETED" || s.status === "ESCALATED") return 1;
  const core = ["primary_symptoms", "symptom_duration", "symptom_severity"];
  const collected = s.progress.collected_fields;
  const coreDone = core.filter((f) => collected.includes(f)).length;
  const extras = collected.filter((f) => !core.includes(f)).length;
  return Math.min(0.95, coreDone * 0.25 + Math.min(extras, 2) * 0.1);
}

function stageLabel(s: ConversationSnapshot): string {
  switch (s.status) {
    case "COMPLETED":
      return "Recommendation ready";
    case "ESCALATED":
      return "Review recommended";
    case "ERROR":
      return "Decision unavailable";
    default:
      return s.progress.core_complete ? "Almost there" : "Getting to know your situation";
  }
}

export function ChatExperience() {
  const params = useSearchParams();
  const starter = TOPIC_STARTERS[params.get("topic") ?? ""] ?? "";
  const { snapshot, messages, sending, busy, fatal, send, retry, correct, retryDecision, startOver } = useConversation();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, sending, snapshot?.recommendation]);

  if (fatal) {
    return (
      <Card className="mx-auto mt-10 max-w-lg p-8 text-center">
        <TriangleAlert aria-hidden className="mx-auto size-8 text-warn" />
        <h1 className="mt-3 text-xl font-medium">We couldn&apos;t start your check</h1>
        <p className="mt-2 text-muted">{fatal.message}</p>
        <Button className="mt-6" onClick={() => window.location.reload()}>
          <RotateCw aria-hidden className="size-4" /> Try again
        </Button>
      </Card>
    );
  }

  const collecting = snapshot?.status === "COLLECTING_INFORMATION";
  const done = snapshot && (snapshot.status === "COMPLETED" || snapshot.status === "ESCALATED");
  const pct = snapshot ? completion(snapshot) : 0;

  const summary = snapshot && (
    <SummaryCard state={snapshot.patientState} editable={!sending && !busy} onCorrect={correct} />
  );

  return (
    <div className="mx-auto grid max-w-6xl gap-5 px-4 pb-6 sm:px-6 lg:grid-cols-[300px_minmax(0,1fr)]">
      {/* Sidebar (desktop) */}
      <aside className="hidden space-y-4 lg:block" aria-label="Your check">
        <Card className="flex flex-col items-center p-6 text-center">
          <ProgressRing value={pct} label="Check progress">
            <span className="text-2xl font-medium">{Math.round(pct * 100)}%</span>
          </ProgressRing>
          <p className="mt-4 font-medium">{snapshot ? stageLabel(snapshot) : "Starting…"}</p>
          {snapshot && collecting && (
            <p className="mt-1 text-sm text-muted">
              Question {Math.min(snapshot.progress.turn + 1, snapshot.progress.max_turns)} of at most{" "}
              {snapshot.progress.max_turns}
            </p>
          )}
        </Card>
        {summary}
        {snapshot && (
          <Link
            href={`/trace/${snapshot.id}`}
            className="flex items-center gap-2 px-2 text-sm text-muted hover:text-ink"
          >
            <Code2 aria-hidden className="size-4" /> Developer view: decision trace
          </Link>
        )}
      </aside>

      {/* Mobile progress + summary */}
      <div className="space-y-3 lg:hidden">
        <div className="flex items-center gap-3 px-1">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-line" aria-hidden>
            <div className="h-full rounded-full bg-ok transition-all duration-500" style={{ width: `${pct * 100}%` }} />
          </div>
          <span className="text-sm text-muted">{snapshot ? stageLabel(snapshot) : "Starting…"}</span>
        </div>
        {summary && (
          <details className="group">
            <summary className="flex cursor-pointer list-none items-center justify-between rounded-full bg-surface px-4 py-2.5 text-sm font-medium shadow-soft">
              What we understood
              <ChevronDown aria-hidden className="size-4 transition-transform group-open:rotate-180" />
            </summary>
            <div className="mt-2">{summary}</div>
          </details>
        )}
      </div>

      {/* Conversation */}
      <section aria-label="Conversation" className="flex min-h-[70dvh] flex-col gap-4 lg:min-h-[calc(100dvh-7rem)]">
        {snapshot?.emergency && <EmergencyBanner crisis={Boolean(snapshot.recommendation?.crisis_support)} />}

        <Card className="flex flex-1 flex-col p-3 sm:p-5">
          <ol className="flex-1 space-y-4 overflow-y-auto p-1 sm:p-2" aria-live="polite" aria-relevant="additions">
            {!snapshot && <TypingIndicator />}
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} onRetry={retry} />
            ))}
            {(sending || busy) && <TypingIndicator />}
          </ol>

          {snapshot?.status === "ERROR" && (
            <div className="mx-1 mt-3 flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-warn-soft p-4 text-sm">
              <span>We couldn&apos;t complete the automated decision.</span>
              <Button variant="dark" className="py-2" disabled={busy} onClick={() => void retryDecision()}>
                <RotateCw aria-hidden className="size-4" /> Try again
              </Button>
            </div>
          )}

          <div className="mt-3">
            {done ? (
              <p className="px-2 text-center text-sm text-muted">
                This check is complete. You can still correct details in the summary.
              </p>
            ) : (
              <Composer
                onSend={send}
                disabled={!collecting || sending || busy}
                initialValue={starter}
                placeholder={messages.length > 1 ? "Type your answer…" : "Describe what's going on…"}
              />
            )}
          </div>
        </Card>

        {snapshot?.recommendation && (
          <RecommendationCard recommendation={snapshot.recommendation} onStartOver={() => void startOver()} />
        )}
        <div ref={endRef} />
      </section>
    </div>
  );
}
