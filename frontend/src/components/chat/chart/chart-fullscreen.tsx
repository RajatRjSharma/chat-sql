"use client";

import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Minimize2, X } from "lucide-react";
import type { ChartDisplayKind, ChartSeries } from "@/lib/chart";
import { cn } from "@/lib/cn";
import { ChartShell } from "./chart-shell";

export function ChartFullscreenModal({
  series,
  activeKind,
  onKindChange,
  showTruncationNote,
  rowCount,
  onClose,
}: {
  series: ChartSeries;
  activeKind: ChartDisplayKind;
  onKindChange: (kind: ChartDisplayKind) => void;
  showTruncationNote: boolean;
  rowCount: number;
  onClose: () => void;
}) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  if (!mounted) return null;

  return createPortal(
    <div className="fixed inset-0 z-[80] flex items-end justify-center p-0 sm:items-center sm:p-5 md:p-8">
      <button
        type="button"
        aria-label="Close fullscreen chart"
        className="absolute inset-0 bg-[var(--bg-shell)]/65 backdrop-blur-[3px] animate-fade-in"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={cn(
          "relative z-[81] flex w-full max-w-5xl flex-col overflow-hidden",
          "h-[min(94dvh,900px)] max-h-[100dvh]",
          "rounded-t-2xl border border-[var(--border-card)] bg-[var(--bg-card)]",
          "shadow-[0_28px_90px_-28px_rgba(15,23,42,0.55)] sm:rounded-2xl",
          "pb-[max(0px,var(--safe-bottom))] animate-rise",
        )}
      >
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-[var(--border-card)] bg-[var(--bg-card)] px-4 py-3.5 pt-[max(0.875rem,var(--safe-top))] sm:px-6 sm:pt-3.5">
          <div className="min-w-0">
            <p
              id={titleId}
              className="font-[family-name:var(--font-display)] text-lg tracking-tight text-[var(--text-primary)]"
            >
              Chart view
            </p>
            <p className="break-words font-mono text-[11px] leading-snug text-[var(--text-secondary)]">
              {series.valueKey} · {series.categoryKey}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden items-center gap-1.5 rounded-md border border-[var(--border-card)] bg-[var(--bg-card)] px-2.5 py-1.5 text-[11px] text-[var(--text-secondary)] sm:inline-flex">
              <Minimize2 className="h-3.5 w-3.5" />
              Esc to close
            </span>
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              aria-label="Close"
              className={cn(
                "inline-flex h-11 w-11 items-center justify-center rounded-md sm:h-10 sm:w-10",
                "border border-[var(--border-card)] bg-[var(--bg-card)] text-[var(--text-primary)]",
                "transition-colors hover:bg-[var(--bg-user)]",
                "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
              )}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
        <div className="min-h-0 flex-1 bg-[var(--bg-card)] px-4 py-4 sm:px-6 sm:py-5">
          <ChartShell
            series={series}
            activeKind={activeKind}
            onKindChange={onKindChange}
            height="100%"
            compact={false}
            showTruncationNote={showTruncationNote}
            rowCount={rowCount}
            expanded
          />
        </div>
      </div>
    </div>,
    document.body,
  );
}
