"use client";

import { Mic, MicOff, SendHorizontal } from "lucide-react";
import { useEffect, useRef, type FormEvent, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useSpeechToText } from "@/hooks/use-speech-to-text";
import { cn } from "@/lib/cn";

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
  const baselineRef = useRef("");

  const { supported, listening, error, toggle, stop } = useSpeechToText({
    disabled: !!disabled,
    onTranscript: (text, { interim }) => {
      const base = baselineRef.current;
      const next = base ? `${base.trimEnd()} ${text}`.trim() : text;
      onChange(next);
      if (!interim) {
        baselineRef.current = next;
      }
    },
  });

  useEffect(() => {
    if (!disabled) ref.current?.focus();
  }, [disabled]);

  useEffect(() => {
    if (disabled) stop();
  }, [disabled, stop]);

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    if (listening) stop();
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

  function handleMicClick() {
    if (disabled) return;
    if (!listening) {
      baselineRef.current = value.trim();
    }
    toggle();
  }

  const hint = listening
    ? "Listening… tap the mic to stop"
    : supported
      ? "Enter to send · Mic to speak"
      : "Enter to send · Voice unsupported in this browser";

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-2xl border border-[var(--border-card)] bg-[var(--bg-card)] p-2.5 shadow-[0_12px_40px_-24px_rgba(15,23,42,0.35)] sm:p-3"
    >
      <Textarea
        ref={ref}
        rows={2}
        value={value}
        onChange={(e) => {
          baselineRef.current = e.target.value;
          onChange(e.target.value);
        }}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={listening ? "Listening…" : placeholder}
        aria-label="Analytics question"
        className="min-h-[3rem] border-0 bg-transparent px-2 py-1 shadow-none focus:ring-0 sm:min-h-0"
      />
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 px-1 sm:flex-nowrap sm:gap-3">
        <div className="order-2 min-w-0 w-full sm:order-1 sm:w-auto">
          <p className="break-words text-[11px] leading-snug text-[var(--text-secondary)]">
            {hint}
          </p>
          {error ? (
            <p role="alert" className="mt-1 break-words text-[11px] text-[var(--error)]">
              {error}
            </p>
          ) : null}
        </div>
        <div className="order-1 ml-auto flex shrink-0 items-center gap-2 sm:order-2 sm:ml-0">
          {supported ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={disabled}
              onClick={handleMicClick}
              aria-label={listening ? "Stop voice input" : "Start voice input"}
              aria-pressed={listening}
              className={cn(
                "min-h-11 min-w-11 px-2.5 text-[var(--text-secondary)] sm:min-h-9 sm:min-w-0",
                listening &&
                  "bg-[var(--accent-soft)] text-[var(--accent-hover)] hover:bg-[var(--accent-soft)] hover:text-[var(--accent-hover)]",
              )}
            >
              {listening ? (
                <span className="relative flex h-4 w-4 items-center justify-center">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--accent)] opacity-40" />
                  <MicOff className="relative h-4 w-4" />
                </span>
              ) : (
                <Mic className="h-4 w-4" />
              )}
            </Button>
          ) : null}
          <Button
            type="submit"
            size="sm"
            disabled={disabled || !value.trim()}
            className="min-h-11 px-4 sm:min-h-9"
          >
            Ask
            <SendHorizontal className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </form>
  );
}
