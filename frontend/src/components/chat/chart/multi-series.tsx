"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartDisplayKind, ChartSeries, MultiSeriesRow } from "@/lib/chart";
import {
  AXIS_TICK,
  DENSE_CATEGORY_COUNT,
  formatValue,
  formatYTick,
  MAX_TICK_CHARS,
  seriesColor,
  TOOLTIP_STYLE,
  truncateLabel,
} from "./chart-shared";

export function MultiSeriesPlot({
  kind,
  series,
}: {
  kind: Extract<ChartDisplayKind, "grouped" | "stacked" | "line">;
  series: ChartSeries;
}) {
  const data = series.multiData ?? [];
  const keys = series.seriesKeys ?? [];
  if (!data.length || !keys.length) return null;

  return (
    <ResponsiveContainer width="100%" height="100%" debounce={50}>
      {kind === "line" ? (
        <MultiLineBody data={data} keys={keys} />
      ) : (
        <MultiBarBody data={data} keys={keys} stacked={kind === "stacked"} />
      )}
    </ResponsiveContainer>
  );
}

function displayLen(data: MultiSeriesRow[]) {
  return Math.max(
    ...data.map((d) => Math.min(String(d.name).length, MAX_TICK_CHARS)),
    1,
  );
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
  const short = truncateLabel(label);
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
        {short}
      </text>
    </g>
  );
}

function multiChrome(data: MultiSeriesRow[]) {
  const maxLen = displayLen(data);
  const dense = data.length >= DENSE_CATEGORY_COUNT;
  const longLabels = maxLen > 8;
  const angled = dense || longLabels || data.length >= 5;
  const xAxisHeight = angled
    ? Math.min(88, Math.max(48, 22 + maxLen * 2.6))
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
      formatter={(value, name) => [
        typeof value === "number" ? formatValue(value) : String(value ?? ""),
        String(name),
      ]}
      labelFormatter={(label) => String(label)}
    />,
    <Legend
      key="legend"
      wrapperStyle={{
        fontSize: 11,
        color: "var(--text-secondary)",
        paddingTop: 4,
      }}
      iconType="circle"
      iconSize={8}
    />,
  ];
}

function multiMargin(data: MultiSeriesRow[]) {
  const maxLen = displayLen(data);
  const angled =
    data.length >= DENSE_CATEGORY_COUNT || maxLen > 8 || data.length >= 5;
  return {
    top: 8,
    right: 12,
    left: 0,
    bottom: angled ? Math.min(28, 8 + Math.floor(maxLen * 0.4)) : 8,
  };
}

function MultiBarBody({
  data,
  keys,
  stacked,
}: {
  data: MultiSeriesRow[];
  keys: string[];
  stacked: boolean;
}) {
  return (
    <BarChart data={data} margin={multiMargin(data)}>
      {multiChrome(data)}
      {keys.map((key, index) => (
        <Bar
          key={key}
          dataKey={key}
          name={key}
          stackId={stacked ? "stack" : undefined}
          fill={seriesColor(index)}
          radius={stacked ? [0, 0, 0, 0] : [3, 3, 0, 0]}
          maxBarSize={stacked ? 56 : 36}
        />
      ))}
    </BarChart>
  );
}

function MultiLineBody({
  data,
  keys,
}: {
  data: MultiSeriesRow[];
  keys: string[];
}) {
  return (
    <LineChart data={data} margin={multiMargin(data)}>
      {multiChrome(data)}
      {keys.map((key, index) => (
        <Line
          key={key}
          type="monotone"
          dataKey={key}
          name={key}
          stroke={seriesColor(index)}
          strokeWidth={2.25}
          dot={{ r: 2.5, fill: seriesColor(index) }}
          activeDot={{ r: 4.5 }}
        />
      ))}
    </LineChart>
  );
}
