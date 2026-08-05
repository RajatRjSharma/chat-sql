import type { ChartDisplayKind } from "@/lib/chart";

export const SERIES_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "#5b9bd5",
  "#0f766e",
  "#64748b",
  "#b45309",
] as const;

/** @deprecated Prefer SERIES_COLORS — kept for pie panel imports. */
export const PIE_COLORS = SERIES_COLORS;

export const KIND_LABELS: Record<ChartDisplayKind, string> = {
  bar: "Bar",
  line: "Line",
  pie: "Pie",
  grouped: "Grouped",
  stacked: "Stacked",
  scatter: "Scatter",
  heatmap: "Heatmap",
};

export const TOOLTIP_STYLE = {
  background: "var(--bg-shell)",
  border: "1px solid var(--border-shell)",
  borderRadius: 8,
  color: "var(--text-on-dark)",
  fontSize: 12,
  maxWidth: 320,
  whiteSpace: "normal" as const,
  wordBreak: "break-word" as const,
  lineHeight: 1.35,
};

export const AXIS_TICK = { fill: "var(--text-secondary)", fontSize: 11 } as const;

export const DENSE_CATEGORY_COUNT = 8;
/** Visible chars on axis ticks; full label stays in tooltip / native title. */
export const MAX_TICK_CHARS = 14;

export function truncateLabel(label: string, maxChars = MAX_TICK_CHARS): string {
  const text = label.trim();
  if (text.length <= maxChars) return text;
  if (maxChars <= 1) return "…";
  return `${text.slice(0, Math.max(1, maxChars - 1))}…`;
}

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

export function seriesColor(index: number): string {
  return SERIES_COLORS[index % SERIES_COLORS.length];
}

export function pieColor(index: number): string {
  return seriesColor(index);
}

/** Blue intensity scale for heatmaps (0 = pale, 1 = strong). */
export function heatFill(t: number): string {
  const clamped = Math.max(0, Math.min(1, t));
  const light = { r: 226, g: 239, b: 251 }; // near --chart-2 wash
  const dark = { r: 37, g: 99, b: 168 }; // --chart-4
  const r = Math.round(light.r + (dark.r - light.r) * clamped);
  const g = Math.round(light.g + (dark.g - light.g) * clamped);
  const b = Math.round(light.b + (dark.b - light.b) * clamped);
  return `rgb(${r}, ${g}, ${b})`;
}
