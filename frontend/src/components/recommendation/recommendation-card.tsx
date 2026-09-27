import { CalendarClock, ChevronRight, MapPin, RotateCcw, ShieldCheck, Stethoscope, UserRoundCheck } from "lucide-react";

import { Button, Card, Chip } from "@/components/ui";
import type { Recommendation } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import { humanize, URGENCY } from "@/lib/labels";

function headline(r: Recommendation): { eyebrow: string; title: string; panel: string } {
  if (r.emergency) return { eyebrow: "Seek care now", title: "Emergency care", panel: URGENCY.EMERGENCY.panel };
  switch (r.action) {
    case "ESCALATE_TO_HUMAN":
      return {
        eyebrow: "Additional review recommended",
        title: "Speak with a healthcare professional",
        panel: "from-[#7462bf] to-[#5a48a8]",
      };
    case "PROVIDE_GENERAL_GUIDANCE":
      return { eyebrow: "Recommended next step", title: "Self-care & monitoring", panel: "from-[#5f8669] to-[#4d7157]" };
    case "REFER_TO_DOCTOR":
      return { eyebrow: "Recommended next step", title: "General physician", panel: URGENCY[r.urgency].panel };
    default:
      return { eyebrow: "Recommended next step", title: r.department_label, panel: URGENCY[r.urgency].panel };
  }
}

export function RecommendationCard({ recommendation: r, onStartOver }: { recommendation: Recommendation; onStartOver: () => void }) {
  const h = headline(r);
  const mapsQuery = r.emergency ? "emergency department near me" : `${r.department_label} clinic near me`;
  return (
    <section aria-labelledby="rec-title" className="animate-rise space-y-3">
      <div className={cn("relative overflow-hidden rounded-panel bg-gradient-to-br p-6 text-white shadow-lift sm:p-8", h.panel)}>
        <span aria-hidden className="absolute -top-16 -right-16 size-56 rounded-full bg-white/10" />
        <span aria-hidden className="absolute right-10 -bottom-20 size-40 rounded-full bg-white/10" />
        <p className="text-sm opacity-85">{h.eyebrow}</p>
        <h2 id="rec-title" className="mt-1 flex flex-wrap items-center gap-3 text-3xl font-medium tracking-tight sm:text-4xl">
          {h.title}
          <Chip className="bg-white/90 text-ink">{r.emergency ? "Urgent" : "Suggested"}</Chip>
        </h2>
        <dl className="relative mt-6 grid gap-2 text-sm sm:grid-cols-2">
          <div className="flex items-center gap-2">
            <CalendarClock aria-hidden className="size-4 opacity-85" />
            <dt className="opacity-85">When:</dt>
            <dd className="font-medium">{URGENCY[r.urgency].label}</dd>
          </div>
          <div className="flex items-center gap-2">
            <Stethoscope aria-hidden className="size-4 opacity-85" />
            <dt className="opacity-85">Case complexity:</dt>
            <dd className="font-medium">{humanize(r.complexity)}</dd>
          </div>
        </dl>
      </div>

      <Card className="p-5 sm:p-6">
        <p className="text-sm text-muted">Next action</p>
        <div className="mt-2 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="flex items-start gap-3 text-lg">
            <MapPin aria-hidden className="mt-1 size-5 shrink-0 text-brand" />
            {r.next_step}
          </p>
          <a
            href={`https://www.google.com/maps/search/${encodeURIComponent(mapsQuery)}`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex shrink-0 items-center justify-center gap-2 rounded-full bg-ink px-5 py-2.5 text-[15px] font-medium text-white shadow-soft hover:bg-ink-soft"
          >
            Find care nearby <ChevronRight aria-hidden className="size-4" />
          </a>
        </div>
      </Card>

      {r.human_review_recommended && !r.emergency && (
        <Card className="flex gap-3 bg-lavender-soft p-5 shadow-none">
          <UserRoundCheck aria-hidden className="size-5 shrink-0 text-lavender" />
          <p className="text-sm text-ink-soft">
            Your information should be reviewed by a healthcare professional. No one has reviewed it yet — please share
            this summary with a doctor.
          </p>
        </Card>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 px-1 pt-1">
        <p className="flex items-center gap-2 text-sm text-muted">
          <ShieldCheck aria-hidden className="size-4" /> A suggestion, not a diagnosis.
        </p>
        <Button variant="outline" onClick={onStartOver} className="py-2">
          <RotateCcw aria-hidden className="size-4" /> Start a new check
        </Button>
      </div>
    </section>
  );
}
