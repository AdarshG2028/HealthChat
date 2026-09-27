import { AlertCircle, RotateCw } from "lucide-react";

import { LogoMark } from "@/components/ui";
import type { ChatMessage } from "@/hooks/use-conversation";
import { cn } from "@/lib/cn";

export function MessageBubble({ message, onRetry }: { message: ChatMessage; onRetry: (m: ChatMessage) => void }) {
  const mine = message.role === "user";
  return (
    <li className={cn("flex animate-rise gap-3", mine ? "justify-end" : "justify-start")}>
      {!mine && (
        <span className="mt-1 grid size-8 shrink-0 place-items-center rounded-full bg-brand-soft text-brand-ink">
          <LogoMark className="h-3.5" />
          <span className="sr-only">Assistant</span>
        </span>
      )}
      <div className={cn("flex max-w-[85%] flex-col sm:max-w-[75%]", mine && "items-end")}>
        <p
          className={cn(
            "rounded-[1.4rem] px-4 py-3 text-[15px] leading-relaxed whitespace-pre-wrap",
            mine ? "rounded-br-md bg-brand-strong text-white" : "rounded-bl-md bg-surface-2 text-ink",
            message.status === "pending" && "opacity-70",
            message.status === "failed" && "bg-danger-soft text-ink ring-1 ring-danger/30",
          )}
        >
          {mine && <span className="sr-only">You: </span>}
          {message.content}
        </p>
        {message.status === "failed" && message.error && (
          <div className="mt-1.5 flex flex-wrap items-center justify-end gap-2 text-sm text-danger" role="alert">
            <AlertCircle aria-hidden className="size-4" />
            <span>{message.error.message}</span>
            {message.error.retryable && (
              <button
                type="button"
                onClick={() => onRetry(message)}
                className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-medium underline-offset-2 hover:underline"
              >
                <RotateCw aria-hidden className="size-3.5" /> Retry
              </button>
            )}
          </div>
        )}
      </div>
    </li>
  );
}

export function TypingIndicator() {
  return (
    <li className="flex gap-3" aria-live="polite">
      <span className="grid size-8 place-items-center rounded-full bg-brand-soft text-brand-ink">
        <LogoMark className="h-3.5" />
      </span>
      <span className="flex items-center gap-1.5 rounded-[1.4rem] rounded-bl-md bg-surface-2 px-4 py-4">
        {[0, 150, 300].map((d) => (
          <span key={d} className="size-2 animate-blink rounded-full bg-muted" style={{ animationDelay: `${d}ms` }} />
        ))}
        <span className="sr-only">The assistant is typing</span>
      </span>
    </li>
  );
}
