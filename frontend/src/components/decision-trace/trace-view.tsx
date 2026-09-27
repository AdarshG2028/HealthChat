"use client";

import { ArrowRight, Braces, Brain, Clock, GitBranch, History, Scale, ShieldAlert, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { ProbabilityBars, ThresholdMeter } from "@/components/decision-trace/probability-bars";
import { Card, Chip } from "@/components/ui";
import { ApiError, apiClient, type Decision, type DecisionTrace, type TraceEvent } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import { humanize, STATE_LABEL, timeOf } from "@/lib/labels";

const HUMAN_REVIEW_THRESHOLD = 0.5;

const EVENT_TONE: Partial<Record<TraceEvent["type"], string>> = {
  JEV_DECISION_COMPLETED: "bg-brand-strong text-white",
  READY_FOR_JEV: "bg-brand-soft text-brand-ink",
  RED_FLAG_DETECTED: "bg-danger text-white",
  JEV_FAILED: "bg-danger-soft text-danger",
  LLM_FAILED: "bg-danger-soft text-danger",
  POLICY_OVERRIDE: "bg-warn-soft text-warn",
  HUMAN_REVIEW_REQUIRED: "bg-lavender-soft text-lavender",
  CONVERSATION_COMPLETED: "bg-sage-soft text-ok-ink",
  EXPLANATION_FALLBACK_USED: "bg-warn-soft text-warn",
};

function SectionTitle({ icon: Icon, tone, children }: { icon: typeof Brain; tone: string; children: React.ReactNode }) {
  return (
    <h2 className="flex items-center gap-3 text-xl font-medium">
      <span className={cn("grid size-8 place-items-center rounded-full", tone)}>
        <Icon aria-hidden className="size-4" />
      </span>
      {children}
    </h2>
  );
}

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <Card className="p-5">
      <p className="text-sm text-muted">{label}</p>
      <p className="mt-1 text-4xl font-medium tabular-nums">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </Card>
  );
}

function DecisionCard({ d, index }: { d: Decision; index: number }) {
  const rows: Array<[string, string, string]> = [
    ["Action", d.action, d.final_action],
    ["Department", d.department, d.final_department],
    ["Urgency", d.urgency, d.final_urgency],
    ["Complexity", d.complexity, d.final_complexity],
  ];
  return (
    <Card className="p-5 sm:p-7">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SectionTitle icon={Scale} tone="bg-brand-soft text-brand-ink">
          Jev decision {index + 1}
        </SectionTitle>
        <div className="flex flex-wrap gap-2 text-xs">
          <Chip className="bg-surface-2 text-ink-soft">{d.provider}</Chip>
          <Chip className="bg-surface-2 text-ink-soft">{d.model_version}</Chip>
          <Chip className="bg-surface-2 text-ink-soft">{d.latency_ms} ms</Chip>
          {d.input_tokens != null && <Chip className="bg-surface-2 text-ink-soft">{d.input_tokens} input tokens</Chip>}
        </div>
      </div>

      <div className="mt-6 grid gap-8 lg:grid-cols-2">
        <div>
          <table className="w-full text-sm">
            <caption className="sr-only">Jev answers and final values after the safety policy</caption>
            <thead>
              <tr className="text-left text-xs tracking-wide text-muted uppercase">
                <th className="pb-2 font-normal">Question</th>
                <th className="pb-2 font-normal">Jev</th>
                <th className="pb-2 font-normal">Final</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map(([q, raw, final]) => (
                <tr key={q}>
                  <td className="py-2.5 text-muted">{q}</td>
                  <td className="py-2.5 font-mono text-xs">{raw}</td>
                  <td className="py-2.5 font-mono text-xs">
                    <span className={cn(raw !== final && "rounded bg-warn-soft px-1.5 py-0.5 text-warn")}>{final}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-6 grid gap-5 sm:grid-cols-2">
            <ThresholdMeter
              label="Human review probability"
              value={d.human_review_probability}
              threshold={HUMAN_REVIEW_THRESHOLD}
            />
            <div className="text-sm">
              <p className="text-muted">Confidence</p>
              <p className="mt-1">
                action <strong className="tabular-nums">{d.action_confidence.toFixed(2)}</strong> · department{" "}
                <strong className="tabular-nums">{d.department_confidence.toFixed(2)}</strong>
              </p>
              <p className="mt-1.5 text-xs text-muted">Below 0.60 escalates to a human</p>
            </div>
          </div>
          {d.policy_overrides.length > 0 && (
            <div className="mt-6">
              <p className="text-xs tracking-wide text-muted uppercase">Safety policy overrides</p>
              <ul className="mt-2 space-y-1.5 text-sm">
                {d.policy_overrides.map((o, i) => (
                  <li key={i} className="flex flex-wrap items-center gap-2">
                    <ShieldAlert aria-hidden className="size-4 text-warn" />
                    <span className="font-mono text-xs">{String(o.field)}</span>
                    <span className="font-mono text-xs text-muted">{String(o.before)}</span>
                    <ArrowRight aria-hidden className="size-3.5" />
                    <span className="font-mono text-xs">{String(o.after)}</span>
                    <span className="text-xs text-muted">({humanize(String(o.rule))})</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <div className="space-y-6">
          {(["department", "urgency", "action"] as const).map((k) =>
            d.probabilities[k] ? (
              <ProbabilityBars key={k} title={`${k} distribution`} distribution={d.probabilities[k]} chosen={d[k]} />
            ) : null,
          )}
        </div>
      </div>

      <details className="group mt-6 rounded-2xl bg-surface-2 p-4">
        <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-medium">
          <Braces aria-hidden className="size-4" /> Jev request (state + questions)
        </summary>
        <pre className="mt-3 max-h-96 overflow-auto text-xs leading-relaxed">{JSON.stringify(d.jev_request, null, 2)}</pre>
      </details>
    </Card>
  );
}

export function TraceView({ id }: { id: string }) {
  const [trace, setTrace] = useState<DecisionTrace | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient
      .trace(id)
      .then(setTrace)
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : "Could not load the trace."));
  }, [id]);

  if (error) return <p className="mx-auto max-w-6xl px-6 py-10 text-danger">{error}</p>;
  if (!trace) return <p className="mx-auto max-w-6xl px-6 py-10 text-muted">Loading trace…</p>;

  const path = trace.workflow_path.filter((s, i, arr) => i === 0 || s !== arr[i - 1]);

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 pb-16 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted">Developer view</p>
          <h1 className="text-4xl font-medium tracking-tight">Decision Trace</h1>
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <Chip className="bg-surface font-mono text-ink-soft shadow-soft">#{trace.conversation_id.slice(0, 8)}</Chip>
            <Chip className="bg-brand-soft text-brand-ink">{STATE_LABEL[trace.status]}</Chip>
            <Chip className="bg-surface text-ink-soft shadow-soft">LLM: {trace.llm_provider}</Chip>
            <Chip className="bg-surface text-ink-soft shadow-soft">Jev: {trace.jev_provider}</Chip>
          </div>
        </div>
        <Link href="/chat" className="text-sm text-muted hover:text-ink">
          ← Back to conversation
        </Link>
      </div>
      <p className="flex items-center gap-2 text-sm text-muted">
        <Sparkles aria-hidden className="size-4" /> Built entirely from stored events and decisions. Viewing it makes no
        model calls.
      </p>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="LLM calls" value={trace.api_calls.llm} hint="1 per turn + 1 explanation" />
        <Stat label="Jev calls" value={trace.api_calls.jev} hint="only at decision points" />
        <Stat label="Turns" value={trace.turn_count} />
        <Stat label="Red flags" value={trace.red_flags.length} hint={trace.red_flags.map(humanize).join(", ") || "none"} />
      </div>

      <Card className="p-5 sm:p-7">
        <SectionTitle icon={GitBranch} tone="bg-sage-soft text-ok-ink">
          Workflow
        </SectionTitle>
        <ol className="mt-5 flex flex-wrap items-center gap-2">
          {path.map((s, i) => (
            <li key={`${s}-${i}`} className="flex items-center gap-2">
              <span
                className={cn(
                  "rounded-full px-3.5 py-1.5 text-sm",
                  s === "JEV_PROCESSING" ? "bg-brand-strong text-white" : "bg-surface-2 text-ink-soft",
                  s === "ERROR" && "bg-danger-soft text-danger",
                )}
              >
                {STATE_LABEL[s]}
              </span>
              {i < path.length - 1 && <ArrowRight aria-hidden className="size-4 text-muted" />}
            </li>
          ))}
        </ol>
        {trace.information_available.length > 0 && (
          <div className="mt-5 flex flex-wrap items-center gap-2 text-sm">
            <span className="text-muted">Information available:</span>
            {trace.information_available.map((f) => (
              <Chip key={f} className="bg-surface-2 text-ink-soft">
                {humanize(f)}
              </Chip>
            ))}
          </div>
        )}
      </Card>

      {trace.decisions.length === 0 ? (
        <Card className="p-7 text-muted">No Jev decision yet: the conversation is still collecting information.</Card>
      ) : (
        trace.decisions.map((d, i) => <DecisionCard key={d.id} d={d} index={i} />)
      )}

      <Card className="p-5 sm:p-7">
        <SectionTitle icon={History} tone="bg-lavender-soft text-lavender">
          Timeline
        </SectionTitle>
        <ol className="mt-5 space-y-1">
          {trace.events.map((e) => (
            <li key={e.id} className="grid grid-cols-[5.5rem_1fr] gap-3 rounded-xl px-2 py-2 text-sm hover:bg-surface-2">
              <span className="flex items-center gap-1.5 text-muted tabular-nums">
                <Clock aria-hidden className="size-3.5" />
                {timeOf(e.created_at)}
              </span>
              <div className="flex flex-wrap items-center gap-2">
                <Chip className={EVENT_TONE[e.type] ?? "bg-surface-2 text-ink-soft"}>{e.type}</Chip>
                {Object.entries(e.data).map(([k, v]) => (
                  <span key={k} className="font-mono text-xs text-muted">
                    {k}=<span className="text-ink-soft">{Array.isArray(v) ? v.join(",") || "[]" : String(v)}</span>
                  </span>
                ))}
              </div>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
