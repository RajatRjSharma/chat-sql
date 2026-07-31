"use client";

import type { ChartDisplayKind } from "@/lib/chart";
import { cn } from "@/lib/cn";
import { KIND_OPTIONS } from "./chart-shared";

export function ChartKindToggle({
  value,
  onChange,
}: {
  value: ChartDisplayKind;
  onChange: (kind: ChartDisplayKind) => void;
}) {
  return (
    <div
      className="flex max-w-full shrink-0 rounded-lg border border-[var(--border-card)] bg-[var(--bg-card)] p-0.5"
      role="group"
      aria-label="Chart type"
    >
      {KIND_OPTIONS.map((opt) => {
        const selected = value === opt.id;
        return (
          <button
            key={opt.id}
            type="button"
            onClick={() => onChange(opt.id)}
            aria-pressed={selected}
            className={cn(
              "min-h-11 rounded-md px-3 py-2 text-[12px] font-medium transition-colors sm:min-h-0 sm:px-2.5 sm:py-1 sm:text-[11px]",
              "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
              selected
                ? "bg-[var(--bg-shell)] text-[var(--text-on-dark)]"
                : "text-[var(--text-secondary)] hover:bg-[var(--bg-user)] hover:text-[var(--text-primary)]",
            )}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
