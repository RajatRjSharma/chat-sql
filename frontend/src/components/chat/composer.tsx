"use client";

import { SendHorizontal } from "lucide-react";
import { useEffect, useRef, type FormEvent, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type ComposerProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (question: string) => void;
  disabled?: boolean;
  placeholder?: string;
};

export function Composer({
  value,
  onChange,
  onSubmit,
  disabled,
  placeholder = "Ask a question about your data…",
}: ComposerProps) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!disabled) ref.current?.focus();
  }, [disabled]);

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    submit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-2xl border border-[var(--border-card)] bg-[var(--bg-card)] p-3 shadow-[0_12px_40px_-24px_rgba(15,23,42,0.35)]"
    >
      <Textarea
        ref={ref}
        rows={2}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={placeholder}
        aria-label="Analytics question"
        className="border-0 bg-transparent px-2 py-1 shadow-none focus:ring-0"
      />
      <div className="mt-2 flex items-center justify-between gap-3 px-1">
        <p className="text-[11px] text-[var(--text-secondary)]">
          Enter to send · Shift+Enter for newline
        </p>
        <Button type="submit" size="sm" disabled={disabled || !value.trim()}>
          Ask
          <SendHorizontal className="h-3.5 w-3.5" />
        </Button>
      </div>
    </form>
  );
}
