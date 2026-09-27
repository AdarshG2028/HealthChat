import type { PatientState, Urgency, WorkflowState } from "@/lib/api/client";

export const BRAND = "Carewise";

/** Summary fields shown to the user, in reading order. */
export const SUMMARY_FIELDS = [
  { key: "primary_symptoms", label: "Main symptom", kind: "list" },
  { key: "symptom_duration", label: "How long", kind: "text" },
  { key: "symptom_severity", label: "Severity", kind: "text" },
  { key: "symptom_frequency", label: "Pattern", kind: "text" },
  { key: "symptom_onset", label: "How it started", kind: "text" },
  { key: "associated_symptoms", label: "Other symptoms", kind: "list" },
  { key: "existing_conditions", label: "Existing conditions", kind: "list" },
  { key: "current_medications", label: "Medications", kind: "list" },
  { key: "known_allergies", label: "Allergies", kind: "list" },
  { key: "age", label: "Age", kind: "number" },
] as const satisfies ReadonlyArray<{ key: keyof PatientState; label: string; kind: "list" | "text" | "number" }>;

export type SummaryField = (typeof SUMMARY_FIELDS)[number];

export function fieldValue(state: PatientState, field: SummaryField): string | null {
  const value = state[field.key];
  if (Array.isArray(value)) return value.length ? value.join(", ") : null;
  if (value === null || value === undefined || value === "") return null;
  return String(value);
}

export const URGENCY: Record<Urgency, { label: string; tone: string; chip: string; panel: string }> = {
  ROUTINE: {
    label: "Routine",
    tone: "text-brand-ink",
    chip: "bg-brand-soft text-brand-ink",
    panel: "from-[#5577ad] to-[#41639a]",
  },
  URGENT: {
    label: "Within 24–48 hours",
    tone: "text-warn",
    chip: "bg-warn-soft text-warn",
    panel: "from-[#94705f] to-[#7a5e50]",
  },
  EMERGENCY: {
    label: "Emergency — now",
    tone: "text-danger",
    chip: "bg-danger-soft text-danger",
    panel: "from-[#c24040] to-[#a52c2c]",
  },
};

export const STATE_LABEL: Record<WorkflowState, string> = {
  COLLECTING_INFORMATION: "Collecting information",
  READY_FOR_DECISION: "Ready for decision",
  JEV_PROCESSING: "Jev deciding",
  EXECUTING_ACTION: "Executing action",
  COMPLETED: "Completed",
  ESCALATED: "Escalated",
  ERROR: "Error",
};

export function humanize(value: string): string {
  return value.charAt(0) + value.slice(1).toLowerCase().replaceAll("_", " ");
}

export function timeOf(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
