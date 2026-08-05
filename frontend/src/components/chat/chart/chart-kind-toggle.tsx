"use client";

import type { ChartDisplayKind } from "@/lib/chart";
import { cn } from "@/lib/cn";
import { KIND_LABELS } from "./chart-shared";

export function ChartKindToggle({
  value,
  onChange,
  options,
}: {
  value: ChartDisplayKind;
  onChange: (kind: ChartDisplayKind) => void;
  options: ChartDisplayKind[];
}) {
  if (options.length <= 1) {
    return (
      <span
        className={cn(
          "inline-flex min-h-11 items-center rounded-lg border border-[var(--border-card)]",
          "bg-[var(--bg-shell)] px-3 py-2 text-[12px] font-medium text-[var(--text-on-dark)]",
          "sm:min-h-0 sm:px-2.5 sm:py-1 sm:text-[11px]",
        )}
        aria-label="Chart type"
      >
        {KIND_LABELS[value]}
      </span>
    );
  }

  return (
    <div
      className="flex max-w-full shrink-0 rounded-lg border border-[var(--border-card)] bg-[var(--bg-card)] p-0.5"
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
              "min-h-11 rounded-md px-3 py-2 text-[12px] font-medium transition-colors sm:min-h-0 sm:px-2.5 sm:py-1 sm:text-[11px]",
              "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
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
