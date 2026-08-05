"use client";

import { Expand } from "lucide-react";
import {
  availableChartKinds,
  chartAxisLabel,
  chartVisibleCount,
  type ChartDisplayKind,
  type ChartSeries,
} from "@/lib/chart";
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
  const axisLabel = chartAxisLabel(series);
  const visible = chartVisibleCount(series);
  const kindOptions = availableChartKinds(series);

  return (
    <div
      className={cn(
        "flex w-full min-w-0 flex-col bg-[var(--bg-card)] animate-fade-in",
        expanded
          ? "h-full overflow-hidden border-0 p-0"
          : "overflow-hidden rounded-xl border border-[var(--border-card)] p-3.5 sm:p-4",
      )}
      style={expanded ? undefined : { height }}
    >
      {/* Title / controls: never overlap — controls stay on their own band */}
      <header
        className={cn(
          "flex shrink-0 flex-col gap-2.5",
          expanded ? "mb-4" : "mb-3",
        )}
      >
        <div className="flex items-center justify-between gap-3">
          <p className="min-w-0 truncate text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
            Visualization
            {showTruncationNote ? (
              <span className="ml-1.5 font-normal normal-case tracking-normal">
                (first {visible} of {rowCount})
              </span>
            ) : null}
          </p>
          <div className="flex shrink-0 items-center gap-1.5">
            <ChartKindToggle
              value={activeKind}
              onChange={onKindChange}
              options={kindOptions}
              compact={compact}
            />
            {onExpand ? (
              <button
                type="button"
                onClick={onExpand}
                aria-label="View chart fullscreen"
                title="Fullscreen"
                className={cn(
                  "inline-flex items-center justify-center rounded-md",
                  compact ? "h-8 w-8" : "h-11 w-11 sm:h-8 sm:w-8",
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
        <p
          className="min-w-0 truncate font-mono text-[11px] leading-snug text-[var(--text-secondary)]"
          title={axisLabel}
        >
          {axisLabel}
        </p>
      </header>

      {/* Plot area: allow axis ticks / legend breathing room */}
      <div className="relative min-h-0 min-w-0 flex-1 overflow-hidden bg-[var(--bg-card)] px-0.5 pb-0.5 outline-none [&_*]:outline-none">
        <ChartPlot
          kind={activeKind}
          series={series}
          compact={compact}
          expanded={expanded}
        />
      </div>
    </div>
  );
}
