import type { ChartDisplayKind } from "@/lib/chart";

export const PIE_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "#5b9bd5",
  "#0f766e",
  "#64748b",
  "#b45309",
] as const;

export const KIND_OPTIONS: { id: ChartDisplayKind; label: string }[] = [
  { id: "bar", label: "Bar" },
  { id: "line", label: "Line" },
  { id: "pie", label: "Pie" },
];

export const TOOLTIP_STYLE = {
  background: "var(--bg-shell)",
  border: "1px solid var(--border-shell)",
  borderRadius: 8,
  color: "var(--text-on-dark)",
  fontSize: 12,
  maxWidth: 240,
} as const;

export const AXIS_TICK = { fill: "var(--text-secondary)", fontSize: 11 } as const;

export const DENSE_CATEGORY_COUNT = 8;

export function formatYTick(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(abs >= 10_000_000 ? 0 : 1)}M`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(abs >= 10_000 ? 0 : 1)}k`;
  if (Number.isInteger(value)) return String(value);
  return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

export function formatValue(value: number): string {
  return Number.isInteger(value)
    ? value.toLocaleString()
    : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function pieColor(index: number): string {
  return PIE_COLORS[index % PIE_COLORS.length];
}
