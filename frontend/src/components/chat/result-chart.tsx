"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { deriveChart } from "@/lib/chart";

type ResultChartProps = {
  columns: string[];
  rows: Record<string, unknown>[];
  compact?: boolean;
};

export function ResultChart({ columns, rows, compact = false }: ResultChartProps) {
  const series = deriveChart(columns, rows);
  if (series.kind === "none") return null;

  const height = compact ? 180 : 280;

  return (
    <div
      className="animate-fade-in rounded-xl border border-[var(--border-card)] bg-[var(--bg-card)] p-4"
      style={{ height }}
    >
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
          Visualization
        </p>
        <p className="truncate font-mono text-[11px] text-[var(--text-secondary)]">
          {series.valueKey} · {series.categoryKey}
        </p>
      </div>
      <div className="h-[calc(100%-1.75rem)] w-full">
        <ResponsiveContainer width="100%" height="100%">
          {series.kind === "line" ? (
            <LineChart data={series.data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="var(--border-card)" strokeDasharray="3 6" vertical={false} />
              <XAxis
                dataKey="name"
                tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={48}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--bg-shell)",
                  border: "1px solid var(--border-shell)",
                  borderRadius: 8,
                  color: "var(--text-on-dark)",
                  fontSize: 12,
                }}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke="var(--chart-1)"
                strokeWidth={2.5}
                dot={{ r: 3, fill: "var(--chart-1)" }}
                activeDot={{ r: 5 }}
              />
            </LineChart>
          ) : (
            <BarChart data={series.data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="var(--border-card)" strokeDasharray="3 6" vertical={false} />
              <XAxis
                dataKey="name"
                tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={48}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--bg-shell)",
                  border: "1px solid var(--border-shell)",
                  borderRadius: 8,
                  color: "var(--text-on-dark)",
                  fontSize: 12,
                }}
              />
              <Bar dataKey="value" fill="var(--chart-1)" radius={[4, 4, 0, 0]} maxBarSize={48} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
