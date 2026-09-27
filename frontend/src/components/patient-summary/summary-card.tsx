"use client";

import { Check, Pencil, X } from "lucide-react";
import { useState } from "react";

import { Card } from "@/components/ui";
import type { ApiError, PatientState, PatientStateUpdate } from "@/lib/api/client";
import { fieldValue, SUMMARY_FIELDS, type SummaryField } from "@/lib/labels";

function toUpdate(field: SummaryField, raw: string): PatientStateUpdate {
  const text = raw.trim();
  if (field.kind === "list") {
    return { [field.key]: text ? text.split(",").map((s) => s.trim()).filter(Boolean) : [] };
  }
  if (field.kind === "number") {
    const n = Number.parseInt(text, 10);
    return { [field.key]: Number.isFinite(n) ? n : null };
  }
  return { [field.key]: text || null };
}

export function SummaryCard({
  state,
  editable,
  onCorrect,
}: {
  state: PatientState;
  editable: boolean;
  onCorrect: (update: PatientStateUpdate) => Promise<ApiError | null>;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const filled = SUMMARY_FIELDS.map((f) => ({ field: f, value: fieldValue(state, f) })).filter((x) => x.value);

  const save = async (field: SummaryField) => {
    setSaving(true);
    const err = await onCorrect(toUpdate(field, draft));
    setSaving(false);
    if (err) setError(err.message);
    else {
      setEditing(null);
      setError(null);
    }
  };

  return (
    <Card className="p-5">
      <h2 className="text-base font-medium">What we understood</h2>
      {filled.length === 0 ? (
        <p className="mt-3 text-sm text-muted">Details you share will appear here, so you can check them.</p>
      ) : (
        <dl className="mt-3 divide-y divide-line">
          {filled.map(({ field, value }) => (
            <div key={field.key} className="py-2.5">
              <dt className="text-xs tracking-wide text-muted uppercase">{field.label}</dt>
              {editing === field.key ? (
                <dd className="mt-1 flex items-center gap-1.5">
                  <label htmlFor={`edit-${field.key}`} className="sr-only">
                    Edit {field.label}
                  </label>
                  <input
                    id={`edit-${field.key}`}
                    autoFocus
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void save(field);
                      if (e.key === "Escape") setEditing(null);
                    }}
                    className="min-w-0 flex-1 rounded-lg border border-line px-2 py-1 text-sm outline-none focus:border-brand"
                  />
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => void save(field)}
                    aria-label={`Save ${field.label}`}
                    className="grid size-7 place-items-center rounded-full bg-ink text-white"
                  >
                    <Check aria-hidden className="size-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditing(null)}
                    aria-label="Cancel"
                    className="grid size-7 place-items-center rounded-full text-muted hover:bg-ink/5"
                  >
                    <X aria-hidden className="size-4" />
                  </button>
                </dd>
              ) : (
                <dd className="group mt-0.5 flex items-start justify-between gap-2 text-[15px]">
                  <span>{value}</span>
                  {editable && (
                    <button
                      type="button"
                      onClick={() => {
                        setEditing(field.key);
                        setDraft(value ?? "");
                        setError(null);
                      }}
                      aria-label={`Correct ${field.label}`}
                      className="grid size-7 shrink-0 place-items-center rounded-full text-muted opacity-60 hover:bg-ink/5 hover:opacity-100"
                    >
                      <Pencil aria-hidden className="size-3.5" />
                    </button>
                  )}
                </dd>
              )}
            </div>
          ))}
        </dl>
      )}
      {error && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {error}
        </p>
      )}
    </Card>
  );
}
