"use client";

import type { ChartDisplayKind } from "@/lib/chart";
import { cn } from "@/lib/cn";
import { KIND_LABELS } from "./chart-shared";

export function ChartKindToggle({
  value,
  onChange,
  options,
  compact = false,
}: {
  value: ChartDisplayKind;
  onChange: (kind: ChartDisplayKind) => void;
  options: ChartDisplayKind[];
  compact?: boolean;
}) {
  if (options.length <= 1) {
    return (
      <span
        className={cn(
          "inline-flex items-center rounded-lg border border-[var(--border-card)]",
          "bg-[var(--bg-shell)] font-medium text-[var(--text-on-dark)]",
          compact
            ? "h-8 px-2.5 text-[11px]"
            : "min-h-11 px-3 py-2 text-[12px] sm:min-h-0 sm:px-2.5 sm:py-1 sm:text-[11px]",
        )}
        aria-label="Chart type"
      >
        {KIND_LABELS[value]}
      </span>
    );
  }

  return (
    <div
      className={cn(
        "flex max-w-full shrink-0 flex-wrap justify-end rounded-lg border border-[var(--border-card)] bg-[var(--bg-card)] p-0.5",
      )}
      role="group"
      aria-label="Chart type"
    >
      {options.map((id) => {
        const selected = value === id;
        return (
          <button
            key={id}
            type="button"
            onClick={() => onChange(id)}
            aria-pressed={selected}
            className={cn(
              "rounded-md font-medium transition-colors",
              "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
              compact
                ? "h-8 px-2 text-[11px]"
                : "min-h-11 px-3 py-2 text-[12px] sm:min-h-0 sm:px-2.5 sm:py-1 sm:text-[11px]",
              selected
                ? "bg-[var(--bg-shell)] text-[var(--text-on-dark)]"
                : "text-[var(--text-secondary)] hover:bg-[var(--bg-user)] hover:text-[var(--text-primary)]",
            )}
          >
            {KIND_LABELS[id]}
          </button>
        );
      })}
    </div>
  );
}
