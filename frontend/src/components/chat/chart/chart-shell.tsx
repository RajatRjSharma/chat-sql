"use client";

import { Expand } from "lucide-react";
import type { ChartDisplayKind, ChartSeries } from "@/lib/chart";
import { cn } from "@/lib/cn";
import { ChartPlot } from "./cartesian";
import { ChartKindToggle } from "./chart-kind-toggle";

export function ChartShell({
  series,
  activeKind,
  onKindChange,
  height,
  compact,
  showTruncationNote,
  rowCount,
  onExpand,
  expanded = false,
}: {
  series: ChartSeries;
  activeKind: ChartDisplayKind;
  onKindChange: (kind: ChartDisplayKind) => void;
  height: number | string;
  compact: boolean;
  showTruncationNote: boolean;
  rowCount: number;
  onExpand?: () => void;
  expanded?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex w-full min-w-0 flex-col overflow-hidden bg-[var(--bg-card)] animate-fade-in",
        expanded
          ? "h-full border-0 p-0"
          : "rounded-xl border border-[var(--border-card)] p-3.5 sm:p-4",
      )}
      style={expanded ? undefined : { height }}
    >
      <div
        className={cn(
          "flex shrink-0 flex-wrap items-start justify-between gap-2",
          expanded ? "mb-4" : "mb-3",
        )}
      >
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
            Visualization
            {showTruncationNote ? (
              <span className="ml-1.5 font-normal normal-case tracking-normal">
                (first {series.data.length} of {rowCount})
              </span>
            ) : null}
          </p>
          <p
            className="break-words font-mono text-[11px] leading-snug text-[var(--text-secondary)]"
            title={`${series.valueKey} · ${series.categoryKey}`}
          >
            {series.valueKey} · {series.categoryKey}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <ChartKindToggle value={activeKind} onChange={onKindChange} />
          {onExpand ? (
            <button
              type="button"
              onClick={onExpand}
              aria-label="View chart fullscreen"
              title="Fullscreen"
              className={cn(
                "inline-flex h-11 w-11 items-center justify-center rounded-md sm:h-8 sm:w-8",
                "border border-[var(--border-card)] bg-[var(--bg-card)]",
                "text-[var(--text-secondary)] transition-colors",
                "hover:bg-[var(--bg-user)] hover:text-[var(--text-primary)]",
                "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
              )}
            >
              <Expand className="h-3.5 w-3.5" />
            </button>
          ) : null}
        </div>
      </div>
      <div className="relative min-h-0 min-w-0 flex-1 overflow-hidden bg-[var(--bg-card)] outline-none [&_*]:outline-none">
        <ChartPlot kind={activeKind} series={series} compact={compact} expanded={expanded} />
      </div>
    </div>
  );
}
