"use client";

import { ArrowUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";

const MAX = 2000;

export function Composer({
  onSend,
  disabled,
  placeholder,
  initialValue = "",
}: {
  onSend: (text: string) => void;
  disabled: boolean;
  placeholder: string;
  initialValue?: string;
}) {
  const [value, setValue] = useState(initialValue);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  useEffect(() => {
    if (!disabled) ref.current?.focus();
  }, [disabled]);

  const submit = () => {
    if (!value.trim() || disabled) return;
    onSend(value);
    setValue("");
  };

  return (
    <form
      className="flex items-end gap-2 rounded-[1.6rem] border border-line bg-surface p-2 pl-4 shadow-soft focus-within:border-brand/50"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <label htmlFor="composer" className="sr-only">
        Your message
      </label>
      <textarea
        id="composer"
        ref={ref}
        rows={1}
        value={value}
        maxLength={MAX}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
        className="max-h-40 flex-1 resize-none bg-transparent py-2 text-[15px] outline-none focus-visible:outline-none placeholder:text-muted disabled:cursor-not-allowed"
      />
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        aria-label="Send message"
        className="grid size-10 shrink-0 place-items-center rounded-full bg-ink text-white transition-opacity disabled:opacity-30"
      >
        <ArrowUp aria-hidden className="size-5" />
      </button>
    </form>
  );
}
