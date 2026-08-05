"use client";

import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import type { ChartSeries } from "@/lib/chart";
import {
  AXIS_TICK,
  formatValue,
  formatYTick,
  TOOLTIP_STYLE,
  truncateLabel,
} from "./chart-shared";

export function ScatterPanel({ series }: { series: ChartSeries }) {
  const data = series.scatterData ?? [];
  const xKey = series.xKey ?? "x";
  const yKey = series.yKey ?? "y";
  if (data.length < 2) return null;

  const xLabel = truncateLabel(xKey, 18);
  const yLabel = truncateLabel(yKey, 18);

  return (
    <ResponsiveContainer width="100%" height="100%" debounce={50}>
      <ScatterChart margin={{ top: 12, right: 20, left: 8, bottom: 28 }}>
        <CartesianGrid stroke="var(--border-card)" strokeDasharray="3 6" />
        <XAxis
          type="number"
          dataKey="x"
          name={xKey}
          tick={AXIS_TICK}
          axisLine={false}
          tickLine={false}
          tickMargin={8}
          height={40}
          tickFormatter={(value) => formatYTick(Number(value))}
          label={{
            value: xLabel,
            position: "insideBottom",
            offset: -2,
            fill: "var(--text-secondary)",
            fontSize: 11,
          }}
        />
        <YAxis
          type="number"
          dataKey="y"
          name={yKey}
          tick={AXIS_TICK}
          axisLine={false}
          tickLine={false}
          width={64}
          tickMargin={6}
          tickFormatter={(value) => formatYTick(Number(value))}
          label={{
            value: yLabel,
            angle: -90,
            position: "insideLeft",
            offset: 4,
            fill: "var(--text-secondary)",
            fontSize: 11,
          }}
        />
        <ZAxis range={[48, 48]} />
        <Tooltip
          cursor={{ strokeDasharray: "3 3", stroke: "var(--border-shell)" }}
          contentStyle={TOOLTIP_STYLE}
          wrapperStyle={{ outline: "none", zIndex: 1 }}
          formatter={(value, name) => [
            typeof value === "number" ? formatValue(value) : String(value ?? ""),
            name === "x" ? xKey : name === "y" ? yKey : String(name),
          ]}
          labelFormatter={(_, payload) => {
            const point = payload?.[0]?.payload as { label?: string } | undefined;
            return point?.label ? String(point.label) : "";
          }}
        />
        <Scatter
          name={`${yKey} vs ${xKey}`}
          data={data}
          fill="var(--chart-1)"
          fillOpacity={0.75}
        />
      </ScatterChart>
    </ResponsiveContainer>
  );
}
