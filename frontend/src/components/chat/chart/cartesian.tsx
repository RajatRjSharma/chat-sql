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
import type { ChartDisplayKind, ChartPoint, ChartSeries } from "@/lib/chart";
import {
  AXIS_TICK,
  DENSE_CATEGORY_COUNT,
  formatValue,
  formatYTick,
  TOOLTIP_STYLE,
} from "./chart-shared";
import { PiePanel } from "./pie-panel";

export function ChartPlot({
  kind,
  series,
  compact,
  expanded,
}: {
  kind: ChartDisplayKind;
  series: ChartSeries;
  compact: boolean;
  expanded: boolean;
}) {
  if (kind === "pie") {
    return <PiePanel data={series.data} compact={compact} expanded={expanded} />;
  }

  return (
    <ResponsiveContainer width="100%" height="100%" debounce={50}>
      {kind === "line" ? <LineBody data={series.data} /> : <BarBody data={series.data} />}
    </ResponsiveContainer>
  );
}

function cartesianChrome(data: ChartPoint[]) {
  const maxLen = Math.max(...data.map((d) => d.name.length), 1);
  const dense = data.length >= DENSE_CATEGORY_COUNT;
  const longLabels = maxLen > 8;
  const angled = dense || longLabels || data.length >= 5;
  // Room for full category names (no ellipsis); scale with longest label.
  const xAxisHeight = angled
    ? Math.min(130, Math.max(56, 24 + maxLen * 3.4))
    : 32;

  return [
    <CartesianGrid
      key="grid"
      stroke="var(--border-card)"
      strokeDasharray="3 6"
      vertical={false}
    />,
    <XAxis
      key="x"
      dataKey="name"
      tick={<CategoryTick angled={angled} />}
      axisLine={false}
      tickLine={false}
      interval={data.length <= 14 ? 0 : "preserveStartEnd"}
      minTickGap={angled ? 2 : 8}
      height={xAxisHeight}
      tickMargin={angled ? 6 : 8}
    />,
    <YAxis
      key="y"
      tick={AXIS_TICK}
      axisLine={false}
      tickLine={false}
      width={52}
      tickFormatter={(value) => formatYTick(Number(value))}
    />,
    <Tooltip
      key="tooltip"
      contentStyle={TOOLTIP_STYLE}
      wrapperStyle={{ outline: "none", zIndex: 1 }}
      formatter={(value) =>
        typeof value === "number" ? formatValue(value) : String(value ?? "")
      }
      labelFormatter={(label) => String(label)}
    />,
  ];
}

function CategoryTick({
  x = 0,
  y = 0,
  payload,
  angled,
}: {
  x?: number;
  y?: number;
  payload?: { value?: string | number };
  angled: boolean;
}) {
  const label = String(payload?.value ?? "");
  return (
    <g transform={`translate(${x},${y})`}>
      <title>{label}</title>
      <text
        dy={angled ? 4 : 12}
        dx={angled ? -2 : 0}
        textAnchor={angled ? "end" : "middle"}
        transform={angled ? "rotate(-38)" : undefined}
        fill="var(--text-secondary)"
        fontSize={11}
        style={{ fontFamily: "var(--font-mono), ui-monospace, monospace" }}
      >
        {label}
      </text>
    </g>
  );
}

function cartesianMargin(data: ChartPoint[]) {
  const maxLen = Math.max(...data.map((d) => d.name.length), 1);
  const angled =
    data.length >= DENSE_CATEGORY_COUNT || maxLen > 8 || data.length >= 5;
  return {
    top: 8,
    right: 12,
    left: 0,
    bottom: angled ? Math.min(36, 10 + Math.floor(maxLen * 0.35)) : 8,
  };
}

function BarBody({ data }: { data: ChartPoint[] }) {
  return (
    <BarChart data={data} margin={cartesianMargin(data)}>
      {cartesianChrome(data)}
      <Bar dataKey="value" fill="var(--chart-1)" radius={[4, 4, 0, 0]} maxBarSize={48} />
    </BarChart>
  );
}

function LineBody({ data }: { data: ChartPoint[] }) {
  return (
    <LineChart data={data} margin={cartesianMargin(data)}>
      {cartesianChrome(data)}
      <Line
        type="monotone"
        dataKey="value"
        stroke="var(--chart-1)"
        strokeWidth={2.5}
        dot={{ r: 3, fill: "var(--chart-1)" }}
        activeDot={{ r: 5 }}
      />
    </LineChart>
  );
}
