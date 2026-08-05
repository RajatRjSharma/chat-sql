"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { ChartPoint } from "@/lib/chart";
import { cn } from "@/lib/cn";
import { formatValue, pieColor, TOOLTIP_STYLE, truncateLabel } from "./chart-shared";

export function PiePanel({
  data,
  compact,
  expanded,
}: {
  data: ChartPoint[];
  compact: boolean;
  expanded: boolean;
}) {
  const total = data.reduce((sum, d) => sum + (Number.isFinite(d.value) ? d.value : 0), 0);
  const stackLegend = compact && !expanded;

  return (
    <div
      className={cn(
        "flex h-full min-h-0 w-full bg-[var(--bg-card)]",
        stackLegend
          ? "flex-col gap-2 sm:flex-row sm:items-stretch sm:gap-3"
          : "flex-row items-stretch gap-3 sm:gap-4",
      )}
    >
      <div
        className={cn(
          "relative min-h-0 min-w-0 bg-[var(--bg-card)]",
          stackLegend
            ? "min-h-[220px] flex-[1.7] sm:h-full sm:min-h-0 sm:flex-[1.75]"
            : "h-full flex-[1.75]",
          expanded && "flex-[1.9]",
        )}
      >
        <ResponsiveContainer width="100%" height="100%" debounce={50}>
          <PieChart>
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              wrapperStyle={{ outline: "none", zIndex: 1 }}
              formatter={(value, _name, item) => {
                const numeric = typeof value === "number" ? value : Number(value);
                const pct =
                  total > 0 && Number.isFinite(numeric)
                    ? ` (${((numeric / total) * 100).toFixed(1)}%)`
                    : "";
                return [`${formatValue(numeric)}${pct}`, String(item?.payload?.name ?? "")];
              }}
            />
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              innerRadius={expanded ? "44%" : compact ? "36%" : "40%"}
              outerRadius={expanded ? "78%" : compact ? "80%" : "76%"}
              paddingAngle={data.length > 1 ? 2 : 0}
              stroke="var(--bg-card)"
              strokeWidth={expanded ? 4 : 3}
              isAnimationActive={!compact}
            >
              {data.map((point, index) => (
                <Cell key={`${point.name}-${index}`} fill={pieColor(index)} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        {total > 0 ? (
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
              Total
            </p>
            <p
              className={cn(
                "mt-0.5 font-mono font-semibold tabular-nums text-[var(--text-primary)]",
                expanded
                  ? "text-lg sm:text-xl"
                  : compact
                    ? "text-[13px] sm:text-sm"
                    : "text-sm sm:text-base",
              )}
            >
              {formatValue(total)}
            </p>
          </div>
        ) : null}
      </div>

      <PieLegend
        data={data}
        total={total}
        compact={compact}
        expanded={expanded}
        stack={stackLegend}
      />
    </div>
  );
}

function PieLegend({
  data,
  total,
  compact,
  expanded,
  stack,
}: {
  data: ChartPoint[];
  total: number;
  compact: boolean;
  expanded: boolean;
  stack: boolean;
}) {
  return (
    <ul
      className={cn(
        // justify-start (not center): centered flex + overflow hides the top of long legends.
        "min-h-0 min-w-0 overflow-y-auto overscroll-contain scroll-pt-1 bg-[var(--bg-card)]",
        stack
          ? "flex max-h-[42%] flex-wrap content-start gap-1.5 sm:max-h-none sm:w-[min(42%,240px)] sm:flex-1 sm:flex-col sm:flex-nowrap sm:justify-start sm:py-1"
          : "flex w-[min(48%,240px)] shrink-0 flex-col justify-start gap-1.5 py-1 sm:w-[min(42%,280px)]",
        expanded && "w-[min(38%,320px)] gap-2 py-1.5",
      )}
      aria-label="Pie chart legend"
    >
      {data.map((point, index) => {
        const pct = total > 0 ? (point.value / total) * 100 : 0;
        return (
          <li
            key={`${point.name}-${index}`}
            className={cn(
              "flex items-start gap-2 rounded-lg border border-[var(--border-card)] bg-[var(--bg-card)]",
              compact && !expanded ? "px-2 py-1.5" : "px-2.5 py-2",
              expanded && "px-3 py-2.5",
              stack && "max-w-full sm:max-w-none",
            )}
          >
            <span
              className="mt-1 h-2.5 w-2.5 shrink-0 rounded-sm"
              style={{ background: pieColor(index) }}
              aria-hidden
            />
            <div className="min-w-0 flex-1">
              <p
                className={cn(
                  "truncate leading-snug text-[var(--text-primary)]",
                  compact && !expanded ? "text-[11px]" : "text-[12px]",
                  expanded && "text-[13px]",
                )}
                title={point.name}
              >
                {truncateLabel(point.name, expanded ? 36 : 22)}
              </p>
              <p className="mt-0.5 break-all font-mono text-[10px] tabular-nums text-[var(--text-secondary)] sm:text-[11px]">
                {formatValue(point.value)}
                <span className="text-[var(--text-secondary)]">
                  {" "}
                  · {pct.toFixed(1)}%
                </span>
              </p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
