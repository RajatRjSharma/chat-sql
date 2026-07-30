"use client";

import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  chartSeriesIdentity,
  deriveChart,
  type ChartDisplayKind,
  type ChartPoint,
  type ChartSeries,
} from "@/lib/chart";
import { cn } from "@/lib/cn";

const PIE_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
] as const;

const KIND_OPTIONS: { id: ChartDisplayKind; label: string }[] = [
  { id: "bar", label: "Bar" },
  { id: "line", label: "Line" },
  { id: "pie", label: "Pie" },
];

const TOOLTIP_STYLE = {
  background: "var(--bg-shell)",
  border: "1px solid var(--border-shell)",
  borderRadius: 8,
  color: "var(--text-on-dark)",
  fontSize: 12,
  maxWidth: 240,
} as const;

const AXIS_TICK = { fill: "var(--text-secondary)", fontSize: 11 } as const;

const DENSE_CATEGORY_COUNT = 8;

type ResultChartProps = {
  columns: string[];
  rows: Record<string, unknown>[];
  compact?: boolean;
};

function truncateLabel(value: unknown, max = 14): string {
  const text = String(value ?? "");
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1)}…`;
}

function formatYTick(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(abs >= 10_000_000 ? 0 : 1)}M`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(abs >= 10_000 ? 0 : 1)}k`;
  if (Number.isInteger(value)) return String(value);
  return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

export function ResultChart({ columns, rows, compact = false }: ResultChartProps) {
  const series = deriveChart(columns, rows);
  const identity = chartSeriesIdentity(series);
  const [pickedKind, setPickedKind] = useState<ChartDisplayKind | null>(null);
  const [baselineIdentity, setBaselineIdentity] = useState(identity);

  // Reset user override when the underlying result set changes (React-recommended).
  if (identity !== baselineIdentity) {
    setBaselineIdentity(identity);
    setPickedKind(null);
  }

  if (series.kind === "none") return null;

  const activeKind: ChartDisplayKind = pickedKind ?? series.kind;
  const height = compact ? 200 : 280;

  return (
    <div
      className="flex w-full min-w-0 flex-col overflow-hidden rounded-xl border border-[var(--border-card)] bg-[var(--bg-card)] p-4 animate-fade-in"
      style={{ height }}
    >
      <div className="mb-3 flex shrink-0 items-start justify-between gap-2">
        <div className="min-w-0 flex-1 overflow-hidden">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
            Visualization
          </p>
          <p className="truncate font-mono text-[11px] text-[var(--text-secondary)]">
            {series.valueKey} · {series.categoryKey}
          </p>
        </div>
        <ChartKindToggle value={activeKind} onChange={setPickedKind} />
      </div>
      <div className="relative min-h-0 min-w-0 flex-1 overflow-hidden">
        <ResponsiveContainer width="100%" height="100%" debounce={50}>
          <ChartBody kind={activeKind} series={series} compact={compact} />
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function ChartKindToggle({
  value,
  onChange,
}: {
  value: ChartDisplayKind;
  onChange: (kind: ChartDisplayKind) => void;
}) {
  return (
    <div
      className="flex max-w-full shrink-0 rounded-lg border border-[var(--border-card)] p-0.5"
      role="group"
      aria-label="Chart type"
    >
      {KIND_OPTIONS.map((opt) => {
        const selected = value === opt.id;
        return (
          <button
            key={opt.id}
            type="button"
            onClick={() => onChange(opt.id)}
            aria-pressed={selected}
            className={cn(
              "rounded-md px-2 py-1 text-[11px] font-medium transition-colors sm:px-2.5",
              "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
              selected
                ? "bg-[var(--bg-shell)] text-[var(--text-on-dark)]"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
            )}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

function ChartBody({
  kind,
  series,
  compact,
}: {
  kind: ChartDisplayKind;
  series: ChartSeries;
  compact: boolean;
}) {
  if (kind === "pie") {
    return <PieBody data={series.data} compact={compact} />;
  }
  if (kind === "line") {
    return <LineBody data={series.data} />;
  }
  return <BarBody data={series.data} />;
}

function cartesianChrome(data: ChartPoint[]) {
  const dense = data.length >= DENSE_CATEGORY_COUNT;
  const longLabels = data.some((d) => d.name.length > 10);
  const angled = dense || longLabels;

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
      tick={AXIS_TICK}
      axisLine={false}
      tickLine={false}
      interval="preserveStartEnd"
      minTickGap={angled ? 4 : 12}
      angle={angled ? -32 : 0}
      textAnchor={angled ? "end" : "middle"}
      height={angled ? 52 : 28}
      tickFormatter={(value) => truncateLabel(value, angled ? 10 : 14)}
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
        typeof value === "number" ? value.toLocaleString() : String(value ?? "")
      }
      labelFormatter={(label) => String(label)}
    />,
  ];
}

function cartesianMargin(data: ChartPoint[]) {
  const angled =
    data.length >= DENSE_CATEGORY_COUNT || data.some((d) => d.name.length > 10);
  return {
    top: 8,
    right: 8,
    left: 0,
    bottom: angled ? 8 : 4,
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

function PieBody({ data, compact }: { data: ChartPoint[]; compact: boolean }) {
  return (
    <PieChart margin={{ top: 4, right: 4, bottom: compact ? 4 : 8, left: 4 }}>
      <Tooltip
        contentStyle={TOOLTIP_STYLE}
        wrapperStyle={{ outline: "none", zIndex: 1 }}
        formatter={(value) =>
          typeof value === "number" ? value.toLocaleString() : String(value ?? "")
        }
      />
      {!compact ? (
        <Legend
          verticalAlign="bottom"
          height={32}
          wrapperStyle={{
            fontSize: 11,
            color: "var(--text-secondary)",
            width: "100%",
            overflow: "hidden",
            paddingTop: 4,
          }}
          formatter={(value) => truncateLabel(value, 18)}
        />
      ) : null}
      <Pie
        data={data}
        dataKey="value"
        nameKey="name"
        cx="50%"
        cy={compact ? "50%" : "44%"}
        innerRadius={compact ? "32%" : "28%"}
        outerRadius={compact ? "70%" : "58%"}
        paddingAngle={2}
        stroke="var(--bg-card)"
        strokeWidth={2}
      >
        {data.map((point, index) => (
          <Cell
            key={`${point.name}-${index}`}
            fill={PIE_COLORS[index % PIE_COLORS.length]}
          />
        ))}
      </Pie>
    </PieChart>
  );
}
