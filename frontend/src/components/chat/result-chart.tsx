"use client";

import {
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Expand, Minimize2, X } from "lucide-react";
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
  "#5b9bd5",
  "#0f766e",
  "#64748b",
  "#b45309",
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

function formatValue(value: number): string {
  return Number.isInteger(value)
    ? value.toLocaleString()
    : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function pieColor(index: number): string {
  return PIE_COLORS[index % PIE_COLORS.length];
}

export function ResultChart({ columns, rows, compact = false }: ResultChartProps) {
  const series = deriveChart(columns, rows);
  const identity = chartSeriesIdentity(series);
  const [pickedKind, setPickedKind] = useState<ChartDisplayKind | null>(null);
  const [baselineIdentity, setBaselineIdentity] = useState(identity);
  const [fullscreen, setFullscreen] = useState(false);

  if (identity !== baselineIdentity) {
    setBaselineIdentity(identity);
    setPickedKind(null);
  }

  if (series.kind === "none") return null;

  const activeKind: ChartDisplayKind = pickedKind ?? series.kind;
  const showTruncationNote =
    series.valueKey !== "count" && rows.length > series.data.length;

  // Pie needs vertical room for a side legend; bar/line stay tighter.
  const height =
    activeKind === "pie" ? (compact ? 260 : 340) : compact ? 200 : 280;

  return (
    <>
      <ChartShell
        series={series}
        activeKind={activeKind}
        onKindChange={setPickedKind}
        height={height}
        compact={compact}
        showTruncationNote={showTruncationNote}
        rowCount={rows.length}
        onExpand={() => setFullscreen(true)}
      />
      {fullscreen ? (
        <ChartFullscreenModal
          series={series}
          activeKind={activeKind}
          onKindChange={setPickedKind}
          showTruncationNote={showTruncationNote}
          rowCount={rows.length}
          onClose={() => setFullscreen(false)}
        />
      ) : null}
    </>
  );
}

function ChartShell({
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
  return (
    <div
      className={cn(
        "flex w-full min-w-0 flex-col overflow-hidden rounded-xl border border-[var(--border-card)] bg-[var(--bg-card)] animate-fade-in",
        expanded ? "h-full rounded-2xl border-0 p-0" : "p-4",
      )}
      style={expanded ? undefined : { height }}
    >
      <div
        className={cn(
          "flex shrink-0 items-start justify-between gap-2",
          expanded ? "mb-4 px-1" : "mb-3",
        )}
      >
        <div className="min-w-0 flex-1 overflow-hidden">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
            Visualization
            {showTruncationNote ? (
              <span className="ml-1.5 font-normal normal-case tracking-normal">
                (first {series.data.length} of {rowCount})
              </span>
            ) : null}
          </p>
          <p className="truncate font-mono text-[11px] text-[var(--text-secondary)]">
            {series.valueKey} · {series.categoryKey}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <ChartKindToggle value={activeKind} onChange={onKindChange} />
          {onExpand ? (
            <button
              type="button"
              onClick={onExpand}
              aria-label="View chart fullscreen"
              title="Fullscreen"
              className={cn(
                "inline-flex h-8 w-8 items-center justify-center rounded-md border border-[var(--border-card)]",
                "text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]",
                "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
              )}
            >
              <Expand className="h-3.5 w-3.5" />
            </button>
          ) : null}
        </div>
      </div>
      <div className="relative min-h-0 min-w-0 flex-1 overflow-hidden">
        <ChartPlot kind={activeKind} series={series} compact={compact} expanded={expanded} />
      </div>
    </div>
  );
}

function ChartFullscreenModal({
  series,
  activeKind,
  onKindChange,
  showTruncationNote,
  rowCount,
  onClose,
}: {
  series: ChartSeries;
  activeKind: ChartDisplayKind;
  onKindChange: (kind: ChartDisplayKind) => void;
  showTruncationNote: boolean;
  rowCount: number;
  onClose: () => void;
}) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  if (!mounted) return null;

  return createPortal(
    <div className="fixed inset-0 z-[80] flex items-end justify-center p-0 sm:items-center sm:p-4 md:p-6">
      <button
        type="button"
        aria-label="Close fullscreen chart"
        className="absolute inset-0 bg-[var(--bg-shell)]/70 backdrop-blur-[2px] animate-fade-in"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={cn(
          "relative z-[81] flex w-full max-w-5xl flex-col",
          "h-[min(92dvh,860px)] max-h-[100dvh]",
          "rounded-t-2xl border border-[var(--border-card)] bg-[var(--bg-surface)] shadow-[0_24px_80px_-24px_rgba(15,23,42,0.55)] sm:rounded-2xl",
          "animate-rise",
        )}
      >
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-[var(--border-card)] px-4 py-3 sm:px-5">
          <div className="min-w-0">
            <p
              id={titleId}
              className="font-[family-name:var(--font-display)] text-lg tracking-tight text-[var(--text-primary)]"
            >
              Chart view
            </p>
            <p className="truncate font-mono text-[11px] text-[var(--text-secondary)]">
              {series.valueKey} · {series.categoryKey}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden items-center gap-1.5 rounded-md border border-[var(--border-card)] px-2.5 py-1.5 text-[11px] text-[var(--text-secondary)] sm:inline-flex">
              <Minimize2 className="h-3.5 w-3.5" />
              Esc to close
            </span>
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              aria-label="Close"
              className={cn(
                "inline-flex h-10 w-10 items-center justify-center rounded-md border border-[var(--border-card)]",
                "bg-[var(--bg-card)] text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-user)]",
                "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
              )}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
        <div className="min-h-0 flex-1 p-4 sm:p-5">
          <ChartShell
            series={series}
            activeKind={activeKind}
            onKindChange={onKindChange}
            height="100%"
            compact={false}
            showTruncationNote={showTruncationNote}
            rowCount={rowCount}
            expanded
          />
        </div>
      </div>
    </div>,
    document.body,
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

function ChartPlot({
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
        typeof value === "number" ? formatValue(value) : String(value ?? "")
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

function PiePanel({
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
        "flex h-full min-h-0 w-full gap-3",
        stackLegend ? "flex-col" : "flex-row items-stretch",
      )}
    >
      <div
        className={cn(
          "relative min-h-0 min-w-0",
          stackLegend ? "h-[58%] w-full" : "h-full flex-[1.35]",
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
              innerRadius={expanded ? "48%" : compact ? "42%" : "46%"}
              outerRadius={expanded ? "78%" : compact ? "72%" : "76%"}
              paddingAngle={data.length > 1 ? 2.5 : 0}
              stroke="var(--bg-card)"
              strokeWidth={3}
              isAnimationActive={!compact}
            >
              {data.map((point, index) => (
                <Cell
                  key={`${point.name}-${index}`}
                  fill={pieColor(index)}
                />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        {total > 0 ? (
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
              Total
            </p>
            <p className="mt-0.5 font-mono text-sm font-medium tabular-nums text-[var(--text-primary)] sm:text-base">
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
        "min-h-0 min-w-0 overflow-y-auto overscroll-contain",
        stack ? "flex max-h-[42%] flex-wrap content-start gap-1.5" : "flex flex-1 flex-col gap-1.5 py-0.5",
        expanded && !stack && "gap-2 pr-1",
      )}
      aria-label="Pie chart legend"
    >
      {data.map((point, index) => {
        const pct = total > 0 ? (point.value / total) * 100 : 0;
        return (
          <li
            key={`${point.name}-${index}`}
            className={cn(
              "flex items-start gap-2 rounded-lg border border-[var(--border-card)]/80 bg-[var(--bg-surface)]/60",
              stack ? "max-w-full px-2 py-1.5" : "px-2.5 py-2",
              expanded && "px-3 py-2.5",
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
                  "leading-snug text-[var(--text-primary)]",
                  compact && !expanded ? "text-[11px]" : "text-[12px]",
                  expanded && "text-[13px]",
                )}
                title={point.name}
              >
                {truncateLabel(point.name, expanded ? 36 : compact ? 16 : 22)}
              </p>
              <p className="mt-0.5 font-mono text-[10px] tabular-nums text-[var(--text-secondary)] sm:text-[11px]">
                {formatValue(point.value)}
                <span className="text-[var(--text-secondary)]/80">
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
