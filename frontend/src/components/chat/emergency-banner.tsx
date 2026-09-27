import { Phone, Siren } from "lucide-react";

/**
 * Static and rendered from `emergency` alone, which the backend sets from deterministic red-flag
 * rules: it shows even if the LLM and Jev are both unavailable.
 */
export function EmergencyBanner({ crisis }: { crisis: boolean }) {
  return (
    <div role="alert" className="animate-rise rounded-card border border-danger/25 bg-danger-soft p-5 text-ink">
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-danger text-white">
          <Siren aria-hidden className="size-5" />
        </span>
        <div className="space-y-2">
          <p className="text-lg font-medium text-danger">This could be a medical emergency</p>
          <p className="text-ink-soft">
            Call your local emergency number now (for example <strong>112</strong>, <strong>911</strong> or{" "}
            <strong>999</strong>) or go to the nearest emergency department. Don&apos;t wait for this chat.
          </p>
          {crisis && (
            <p className="text-ink-soft">
              If you&apos;re thinking about harming yourself, please reach out right now: <strong>988</strong> (US),{" "}
              <strong>116 123</strong> (UK &amp; EU) or <strong>14416</strong> Tele-MANAS (India).
            </p>
          )}
          <a
            href="tel:112"
            className="inline-flex items-center gap-2 rounded-full bg-danger px-4 py-2 text-sm font-medium text-white"
          >
            <Phone aria-hidden className="size-4" /> Call emergency services
          </a>
        </div>
      </div>
    </div>
  );
}
