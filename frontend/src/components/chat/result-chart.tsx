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
} as const;

const AXIS_TICK = { fill: "var(--text-secondary)", fontSize: 11 } as const;

type ResultChartProps = {
  columns: string[];
  rows: Record<string, unknown>[];
  compact?: boolean;
};

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
  const height = compact ? 200 : 300;

  return (
    <div
      className="animate-fade-in rounded-xl border border-[var(--border-card)] bg-[var(--bg-card)] p-4"
      style={{ height }}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
            Visualization
          </p>
          <p className="truncate font-mono text-[11px] text-[var(--text-secondary)]">
            {series.valueKey} · {series.categoryKey}
          </p>
        </div>
        <ChartKindToggle value={activeKind} onChange={setPickedKind} />
      </div>
      <div className="h-[calc(100%-2.75rem)] w-full">
        <ResponsiveContainer width="100%" height="100%">
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
      className="flex shrink-0 rounded-lg border border-[var(--border-card)] p-0.5"
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
              "rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors",
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

function cartesianChrome() {
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
    />,
    <YAxis
      key="y"
      tick={AXIS_TICK}
      axisLine={false}
      tickLine={false}
      width={48}
    />,
    <Tooltip key="tooltip" contentStyle={TOOLTIP_STYLE} />,
  ];
}

function BarBody({ data }: { data: ChartPoint[] }) {
  return (
    <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
      {cartesianChrome()}
      <Bar dataKey="value" fill="var(--chart-1)" radius={[4, 4, 0, 0]} maxBarSize={48} />
    </BarChart>
  );
}

function LineBody({ data }: { data: ChartPoint[] }) {
  return (
    <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
      {cartesianChrome()}
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
    <PieChart>
      <Tooltip contentStyle={TOOLTIP_STYLE} />
      {!compact ? (
        <Legend
          verticalAlign="bottom"
          height={28}
          wrapperStyle={{ fontSize: 11, color: "var(--text-secondary)" }}
        />
      ) : null}
      <Pie
        data={data}
        dataKey="value"
        nameKey="name"
        cx="50%"
        cy={compact ? "50%" : "46%"}
        innerRadius={compact ? 28 : 40}
        outerRadius={compact ? 58 : 72}
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
