import { ChevronRight, HeartPulse, Lock, MessageCircle, ShieldAlert } from "lucide-react";
import Link from "next/link";

import { ButtonLink, Logo } from "@/components/ui";

const PROMISES = [
  { icon: MessageCircle, text: "Asks only what matters" },
  { icon: ShieldAlert, text: "Emergency-aware" },
  { icon: Lock, text: "Private by design" },
  { icon: HeartPulse, text: "Free, no sign-up" },
];

export function PromiseStrip() {
  return (
    <div className="hidden bg-sky/60 text-sm text-ink-soft md:block">
      <ul className="mx-auto flex max-w-6xl items-center justify-between gap-6 px-6 py-2.5">
        <li className="border-r border-ink/15 pr-6 font-medium text-ink">Why Carewise?</li>
        {PROMISES.map(({ icon: Icon, text }) => (
          <li key={text} className="flex items-center gap-2">
            <Icon aria-hidden className="size-4 text-ink-soft/80" />
            {text}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SiteHeader({ compact = false }: { compact?: boolean }) {
  return (
    <header>
      {!compact && <PromiseStrip />}
      <nav aria-label="Main" className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-5 sm:px-6">
        <Link href="/" aria-label="Carewise home">
          <Logo />
        </Link>
        <ul className="hidden items-center gap-8 text-[15px] text-ink-soft md:flex">
          <li>
            <Link href="/#how-it-works" className="hover:text-ink">
              How it works
            </Link>
          </li>
          <li>
            <Link href="/#safety" className="hover:text-ink">
              Safety
            </Link>
          </li>
        </ul>
        <ButtonLink href="/chat" variant="outline" className="py-2 pr-4">
          Start a check <ChevronRight aria-hidden className="size-4" />
        </ButtonLink>
      </nav>
    </header>
  );
}
