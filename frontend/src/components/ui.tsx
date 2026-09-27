import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/cn";

type ButtonVariant = "dark" | "outline" | "ghost" | "light";

const buttonStyles: Record<ButtonVariant, string> = {
  dark: "bg-ink text-white hover:bg-ink-soft shadow-soft",
  outline: "border border-line bg-surface text-ink hover:border-ink/30",
  ghost: "text-ink-soft hover:bg-ink/5",
  light: "bg-white/90 text-ink hover:bg-white shadow-soft",
};

const base =
  "inline-flex items-center justify-center gap-2 rounded-full px-5 py-2.5 text-[15px] font-medium transition-colors disabled:pointer-events-none disabled:opacity-50";

export function Button({ variant = "dark", className, ...props }: ComponentProps<"button"> & { variant?: ButtonVariant }) {
  return <button className={cn(base, buttonStyles[variant], className)} {...props} />;
}

export function ButtonLink({
  variant = "dark",
  className,
  ...props
}: ComponentProps<typeof Link> & { variant?: ButtonVariant }) {
  return <Link className={cn(base, buttonStyles[variant], className)} {...props} />;
}

export function Card({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("rounded-card bg-surface shadow-soft", className)} {...props} />;
}

export function Pill({ className, children, dot }: { className?: string; children: ReactNode; dot?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full bg-surface px-3.5 py-1.5 text-sm text-ink-soft shadow-soft",
        className,
      )}
    >
      {dot && <span aria-hidden className={cn("size-2 rounded-full", dot)} />}
      {children}
    </span>
  );
}

export function Chip({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <span className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium", className)}>
      {children}
    </span>
  );
}

/** The brand mark: a rounded capsule split by a path, echoing "finding a way through". */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 28" className={cn("h-6 w-auto", className)} aria-hidden>
      <rect x="0" y="0" width="40" height="28" rx="14" fill="currentColor" />
      <path d="M13 21c3-9 11-5 14-14" stroke="white" strokeWidth="3.2" strokeLinecap="round" fill="none" />
      <circle cx="13" cy="21" r="2.4" fill="white" />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5 text-ink", className)}>
      <LogoMark />
      <span className="text-lg font-medium tracking-[0.28em] uppercase">Carewise</span>
    </span>
  );
}
