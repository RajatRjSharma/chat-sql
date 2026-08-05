"use client";

import type { ChartSeries, HeatCell } from "@/lib/chart";
import { cn } from "@/lib/cn";
import { formatValue, heatFill, truncateLabel } from "./chart-shared";

export function HeatmapPanel({
  series,
  compact,
}: {
  series: ChartSeries;
  compact: boolean;
}) {
  const rows = series.heatRows ?? [];
  const cols = series.heatCols ?? [];
  const cells = series.heatData ?? [];
  if (!rows.length || !cols.length) return null;

  const lookup = new Map<string, number>();
  for (const cell of cells) {
    lookup.set(`${cell.row}\0${cell.col}`, cell.value);
  }

  const values = cells.map((c) => c.value);
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 1;
  const span = max - min || 1;

  function intensity(value: number | undefined): number {
    if (value == null) return 0;
    return (value - min) / span;
  }

  function cellAt(row: string, col: string): HeatCell | null {
    const value = lookup.get(`${row}\0${col}`);
    if (value == null) return null;
    return { row, col, value };
  }

  const colLabelChars = compact ? 8 : 10;
  const rowLabelChars = compact ? 10 : 14;

  return (
    <div className="flex h-full min-h-0 w-full flex-col gap-2 overflow-hidden">
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-max min-w-full border-separate border-spacing-1">
          <thead>
            <tr>
              <th className="sticky left-0 z-[1] bg-[var(--bg-card)] p-0" />
              {cols.map((col) => (
                <th
                  key={col}
                  title={col}
                  className={cn(
                    "px-1 pb-1 text-center font-mono text-[10px] font-medium",
                    "text-[var(--text-secondary)]",
                  )}
                >
                  {truncateLabel(col, colLabelChars)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row}>
                <th
                  title={row}
                  className={cn(
                    "sticky left-0 z-[1] max-w-[7.5rem] bg-[var(--bg-card)] pr-2 text-left",
                    "font-mono text-[10px] font-medium text-[var(--text-secondary)]",
                  )}
                >
                  {truncateLabel(row, rowLabelChars)}
                </th>
                {cols.map((col) => {
                  const cell = cellAt(row, col);
                  const t = intensity(cell?.value);
                  const empty = cell == null;
                  return (
                    <td key={col} className="p-0">
                      <div
                        title={
                          empty
                            ? `${row} × ${col}: —`
                            : `${row} × ${col}: ${formatValue(cell.value)}`
                        }
                        className={cn(
                          "flex h-8 min-w-[2.25rem] items-center justify-center rounded-sm",
                          "font-mono text-[10px] tabular-nums transition-opacity",
                          "sm:h-9 sm:min-w-[2.75rem]",
                          empty && "border border-dashed border-[var(--border-card)]",
                        )}
                        style={
                          empty
                            ? { color: "var(--text-secondary)", background: "transparent" }
                            : {
                                background: heatFill(t),
                                color: t > 0.55 ? "#f8fafc" : "var(--text-primary)",
                              }
                        }
                      >
                        {empty ? "" : formatValue(cell.value)}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex shrink-0 items-center gap-2 px-0.5">
        <span className="font-mono text-[10px] text-[var(--text-secondary)]">
          {formatValue(min)}
        </span>
        <div
          className="h-2 flex-1 rounded-sm"
          style={{
            background: `linear-gradient(90deg, ${heatFill(0)}, ${heatFill(1)})`,
          }}
          aria-hidden
        />
        <span className="font-mono text-[10px] text-[var(--text-secondary)]">
          {formatValue(max)}
        </span>
      </div>
    </div>
  );
}
