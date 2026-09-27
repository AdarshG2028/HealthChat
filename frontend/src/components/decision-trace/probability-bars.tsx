import { cn } from "@/lib/cn";
import { humanize } from "@/lib/labels";

export function ProbabilityBars({
  title,
  distribution,
  chosen,
  limit = 5,
}: {
  title: string;
  distribution: Record<string, number>;
  chosen: string;
  limit?: number;
}) {
  const rows = Object.entries(distribution)
    .sort(([, a], [, b]) => b - a)
    .slice(0, limit);
  return (
    <figure>
      <figcaption className="text-xs tracking-wide text-muted uppercase">{title}</figcaption>
      <ul className="mt-2 space-y-2">
        {rows.map(([label, p]) => (
          <li key={label} className="grid grid-cols-[minmax(0,9rem)_1fr_3rem] items-center gap-3 text-sm">
            <span className={cn("truncate", label === chosen ? "font-medium text-ink" : "text-muted")}>
              {humanize(label)}
            </span>
            <span className="h-2 overflow-hidden rounded-full bg-line" aria-hidden>
              <span
                className={cn("block h-full rounded-full", label === chosen ? "bg-brand" : "bg-sky")}
                style={{ width: `${Math.max(2, p * 100)}%` }}
              />
            </span>
            <span className="text-right tabular-nums text-ink-soft">{(p * 100).toFixed(0)}%</span>
          </li>
        ))}
      </ul>
    </figure>
  );
}

/** Range meter with a threshold marker (like a lab-result range bar). */
export function ThresholdMeter({ value, threshold, label }: { value: number; threshold: number; label: string }) {
  return (
    <div>
      <div className="flex items-baseline justify-between text-sm">
        <span className="text-muted">{label}</span>
        <span className="font-medium tabular-nums">{value.toFixed(2)}</span>
      </div>
      <div className="relative mt-2 h-2 rounded-full bg-line" aria-hidden>
        <span className="absolute inset-y-0 left-0 rounded-full bg-ok/70" style={{ width: `${threshold * 100}%` }} />
        <span
          className="absolute -top-1.5 h-5 w-0.5 rounded bg-ink"
          style={{ left: `calc(${value * 100}% - 1px)` }}
        />
      </div>
      <p className="mt-1.5 text-xs text-muted">Escalates at ≥ {threshold.toFixed(2)}</p>
    </div>
  );
}
