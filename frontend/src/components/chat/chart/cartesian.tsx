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
  cartesianPlotMargin,
  DENSE_CATEGORY_COUNT,
  formatValue,
  formatYTick,
  MAX_TICK_CHARS,
  TOOLTIP_STYLE,
  truncateLabel,
  xAxisTickHeight,
} from "./chart-shared";
import { HeatmapPanel } from "./heatmap-panel";
import { MultiSeriesPlot } from "./multi-series";
import { PiePanel } from "./pie-panel";
import { ScatterPanel } from "./scatter-panel";

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

  if (kind === "scatter" || series.family === "scatter") {
    return <ScatterPanel series={series} />;
  }

  if (kind === "heatmap" || series.family === "heatmap") {
    return <HeatmapPanel series={series} compact={compact} />;
  }

  if (
    series.family === "multi" &&
    (kind === "grouped" || kind === "stacked" || kind === "line")
  ) {
    return <MultiSeriesPlot kind={kind} series={series} />;
  }

  // Classic single-series bar / line (and multi falling back if mis-routed)
  if (kind === "grouped" || kind === "stacked") {
    return (
      <ResponsiveContainer width="100%" height="100%" debounce={50}>
        <BarBody data={series.data} />
      </ResponsiveContainer>
    );
  }

  return (
    <ResponsiveContainer width="100%" height="100%" debounce={50}>
      {kind === "line" ? <LineBody data={series.data} /> : <BarBody data={series.data} />}
    </ResponsiveContainer>
  );
}

function displayLen(data: ChartPoint[]) {
  return Math.max(
    ...data.map((d) => Math.min(d.name.length, MAX_TICK_CHARS)),
    1,
  );
}

function angledMeta(data: ChartPoint[]) {
  const maxLen = displayLen(data);
  const dense = data.length >= DENSE_CATEGORY_COUNT;
  const longLabels = maxLen > 8;
  const angled = dense || longLabels || data.length >= 5;
  return { maxLen, angled };
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
        dy={angled ? 6 : 10}
        dx={angled ? -1 : 0}
        textAnchor={angled ? "end" : "middle"}
        transform={angled ? "rotate(-35)" : undefined}
        fill="var(--text-secondary)"
        fontSize={11}
        style={{ fontFamily: "var(--font-mono), ui-monospace, monospace" }}
      >
        {short}
      </text>
    </g>
  );
}

function cartesianChrome(data: ChartPoint[]) {
  const { maxLen, angled } = angledMeta(data);

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
      interval={data.length <= 12 ? 0 : "preserveStartEnd"}
      minTickGap={angled ? 4 : 10}
      height={xAxisTickHeight(angled, maxLen)}
      tickMargin={angled ? 8 : 6}
      padding={{ left: 8, right: 8 }}
    />,
    <YAxis
      key="y"
      tick={AXIS_TICK}
      axisLine={false}
      tickLine={false}
      width={56}
      tickMargin={6}
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

function BarBody({ data }: { data: ChartPoint[] }) {
  const { maxLen, angled } = angledMeta(data);
  return (
    <BarChart
      data={data}
      margin={cartesianPlotMargin({ angled, maxLabelChars: maxLen })}
    >
      {cartesianChrome(data)}
      <Bar dataKey="value" fill="var(--chart-1)" radius={[4, 4, 0, 0]} maxBarSize={48} />
    </BarChart>
  );
}

function LineBody({ data }: { data: ChartPoint[] }) {
  const { maxLen, angled } = angledMeta(data);
  return (
    <LineChart
      data={data}
      margin={cartesianPlotMargin({ angled, maxLabelChars: maxLen })}
    >
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
