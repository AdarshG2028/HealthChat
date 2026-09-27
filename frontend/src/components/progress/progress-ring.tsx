import { cn } from "@/lib/cn";

/** Tick ring: ticks fill clockwise with progress. */
export function ProgressRing({
  value,
  size = 112,
  ticks = 48,
  className,
  children,
  label,
}: {
  value: number;
  size?: number;
  ticks?: number;
  className?: string;
  children?: React.ReactNode;
  label: string;
}) {
  const filled = Math.round(Math.max(0, Math.min(1, value)) * ticks);
  const c = size / 2;
  // Rounded so server- and client-rendered markup are byte-identical (no hydration mismatch).
  const r2d = (n: number) => Math.round(n * 100) / 100;
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(value * 100)}
      className={cn("relative grid place-items-center", className)}
      style={{ width: size, height: size }}
    >
      <svg viewBox={`0 0 ${size} ${size}`} className="absolute inset-0" aria-hidden>
        {Array.from({ length: ticks }, (_, i) => {
          const angle = (i / ticks) * 2 * Math.PI - Math.PI / 2;
          const r1 = c - 4;
          const r2 = c - (i % 4 === 0 ? 15 : 12);
          return (
            <line
              key={i}
              x1={r2d(c + r1 * Math.cos(angle))}
              y1={r2d(c + r1 * Math.sin(angle))}
              x2={r2d(c + r2 * Math.cos(angle))}
              y2={r2d(c + r2 * Math.sin(angle))}
              strokeWidth={2.2}
              strokeLinecap="round"
              className={cn("transition-colors duration-500", i < filled ? "stroke-ok" : "stroke-line")}
            />
          );
        })}
      </svg>
      <div className="relative">{children}</div>
    </div>
  );
}
