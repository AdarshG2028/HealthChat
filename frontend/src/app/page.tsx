import {
  ArrowUpRight,
  Brain,
  Check,
  ChevronRight,
  ClipboardList,
  MessageSquareText,
  Route,
  Soup,
  Sparkles,
  Wind,
} from "lucide-react";
import Link from "next/link";

import { SiteHeader } from "@/components/layout/site-header";
import { ButtonLink, Card, Pill } from "@/components/ui";
import { cn } from "@/lib/cn";

const TOPICS = [
  {
    slug: "stomach",
    eyebrow: "Digestion",
    title: "Stomach pain & nausea",
    icon: Soup,
    card: "bg-taupe text-white",
    glow: "bg-white/15",
  },
  {
    slug: "headache",
    eyebrow: "Head & nerves",
    title: "Headaches & dizziness",
    icon: Brain,
    card: "bg-lavender text-white",
    glow: "bg-white/15",
  },
  {
    slug: "skin",
    eyebrow: "Skin",
    title: "Rashes & itching",
    icon: Sparkles,
    card: "bg-sage text-white",
    glow: "bg-white/15",
  },
  {
    slug: "breathing",
    eyebrow: "Chest & lungs",
    title: "Coughs & breathing",
    icon: Wind,
    card: "bg-brand-strong text-white",
    glow: "bg-white/15",
  },
];

const STEPS = [
  {
    icon: MessageSquareText,
    title: "Tell us what's going on",
    body: "In your own words. No long forms, no medical jargon needed.",
  },
  {
    icon: ClipboardList,
    title: "Answer a few questions",
    body: "Only the ones that matter for your situation. You can correct anything we got wrong.",
  },
  {
    icon: Route,
    title: "Get a clear next step",
    body: "Which kind of care, and how soon, with a plain-language explanation of why.",
  },
];

const SAFETY = [
  "Emergency warning signs are checked on every message, even if our AI is unavailable",
  "Never diagnoses, never suggests medication",
  "Uncertain or complex cases are flagged for a healthcare professional",
  "Your answers are never used in analytics or logs",
];

export default function Home() {
  return (
    <>
      <SiteHeader />
      <main>
        {/* Hero */}
        <section className="mx-auto max-w-6xl px-5 pt-10 text-center sm:px-6 sm:pt-16">
          <Pill dot="bg-ok" className="animate-rise">
            AI-guided health navigation · Not a diagnosis
          </Pill>
          <h1 className="mx-auto mt-6 max-w-3xl text-[2.6rem] leading-[1.05] font-medium tracking-tight text-balance sm:text-6xl">
            Not sure where to go?
            <br />
            <span className="text-brand-strong">Find your next step.</span>
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-lg text-muted">
            Describe your symptoms in a short conversation and get a safety-first suggestion for the right kind of care.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <ButtonLink href="/chat" className="px-7 py-3.5 text-base">
              Start a check <ChevronRight aria-hidden className="size-4" />
            </ButtonLink>
            <span className="text-sm text-muted">Takes about 2 minutes</span>
          </div>
        </section>

        {/* Topic cards */}
        <section aria-labelledby="topics" className="mx-auto mt-14 max-w-6xl px-5 sm:px-6">
          <h2 id="topics" className="sr-only">
            Start with a common concern
          </h2>
          <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {TOPICS.map(({ slug, eyebrow, title, icon: Icon, card, glow }, i) => (
              <li key={slug} className="animate-rise" style={{ animationDelay: `${i * 70}ms` }}>
                <Link
                  href={`/chat?topic=${slug}`}
                  className={cn(
                    "group relative flex h-64 flex-col overflow-hidden rounded-panel p-6 shadow-lift transition-transform hover:-translate-y-1 lg:h-80",
                    card,
                  )}
                >
                  <span className="pr-14 text-sm">{eyebrow}</span>
                  <span className="mt-2 pr-12 text-3xl leading-tight font-medium">{title}</span>
                  <span
                    aria-hidden
                    className="absolute top-5 right-5 grid size-11 place-items-center rounded-full bg-white/20 transition-colors group-hover:bg-white/35"
                  >
                    <ArrowUpRight className="size-5" />
                  </span>
                  <span aria-hidden className={cn("absolute -right-10 -bottom-10 size-48 rounded-full", glow)} />
                  <Icon aria-hidden strokeWidth={1.25} className="absolute right-6 bottom-6 size-24 opacity-90" />
                </Link>
              </li>
            ))}
          </ul>
        </section>

        {/* How it works */}
        <section id="how-it-works" className="mx-auto mt-24 max-w-6xl scroll-mt-8 px-5 sm:px-6">
          <h2 className="text-3xl font-medium tracking-tight sm:text-4xl">
            How it <span className="text-brand">works</span>
          </h2>
          <ol className="mt-8 grid gap-4 md:grid-cols-3">
            {STEPS.map(({ icon: Icon, title, body }, i) => (
              <li key={title}>
              <Card className="h-full bg-surface-2 p-7">
                <div className="flex items-center justify-between">
                  <span className="grid size-8 place-items-center rounded-lg bg-ink text-sm font-medium text-white">
                    {i + 1}
                  </span>
                  <Icon aria-hidden strokeWidth={1.5} className="size-8 text-brand" />
                </div>
                <h3 className="mt-10 text-xl font-medium">{title}</h3>
                <p className="mt-2 text-muted">{body}</p>
              </Card>
              </li>
            ))}
          </ol>
        </section>

        {/* Safety */}
        <section id="safety" className="mx-auto mt-24 max-w-6xl scroll-mt-8 px-5 sm:px-6">
          <div className="grid overflow-hidden rounded-panel bg-gradient-to-br from-[#5577ad] to-[#41639a] text-white shadow-lift lg:grid-cols-[1.2fr_1fr]">
            <div className="p-8 sm:p-12">
              <p className="text-sm opacity-80">Built safety-first</p>
              <h2 className="mt-3 text-4xl leading-tight font-medium tracking-tight sm:text-5xl">
                Clear guidance.
                <br />
                No guesswork.
              </h2>
              <ul className="mt-8 space-y-3.5">
                {SAFETY.map((line) => (
                  <li key={line} className="flex gap-3">
                    <Check aria-hidden className="mt-0.5 size-5 shrink-0 rounded-full bg-white p-0.5 text-brand" />
                    <span className="opacity-95">{line}</span>
                  </li>
                ))}
              </ul>
              <ButtonLink href="/chat" className="mt-10">
                Start a check <ChevronRight aria-hidden className="size-4" />
              </ButtonLink>
            </div>
            <div className="grid grid-cols-2 gap-3 p-6 sm:p-8 lg:grid-cols-1 lg:content-center">
              {[
                ["1", "decision per check, made by a typed decision model, not free text"],
                ["8", "questions at most — then you get an answer"],
                ["0", "diagnoses or prescriptions, ever"],
              ].map(([n, text]) => (
                <div key={text} className="rounded-card bg-black/15 p-5 ring-1 ring-white/15">
                  <p className="text-5xl font-medium">{n}</p>
                  <p className="mt-2 text-sm opacity-90">{text}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <footer className="mx-auto mt-20 max-w-6xl px-5 pb-12 text-sm text-muted sm:px-6">
          <p className="max-w-3xl">
            Carewise is a portfolio prototype that suggests a general healthcare pathway. It does not diagnose, treat or
            replace a medical professional. If you think you may be having a medical emergency, call your local
            emergency number immediately.
          </p>
        </footer>
      </main>
    </>
  );
}
