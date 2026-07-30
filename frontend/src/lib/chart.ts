export type ChartKind = "bar" | "line" | "pie" | "none";

export type ChartDisplayKind = Exclude<ChartKind, "none">;

export type ChartPoint = { name: string; value: number };

export type ChartSeries = {
  kind: ChartKind;
  categoryKey: string;
  valueKey: string;
  data: ChartPoint[];
};

const EMPTY_SERIES: ChartSeries = {
  kind: "none",
  categoryKey: "",
  valueKey: "",
  data: [],
};

const MAX_CHART_ROWS = 40;
const PIE_MAX_CATEGORIES = 8;
const LINE_MIN_ROWS = 13;

function isNumeric(value: unknown): boolean {
  if (typeof value === "number" && Number.isFinite(value)) return true;
  if (typeof value === "string" && value.trim() !== "" && !Number.isNaN(Number(value))) {
    return true;
  }
  return false;
}

function toNumber(value: unknown): number {
  return typeof value === "number" ? value : Number(value);
}

/** Default visualization when the user has not picked a chart type. */
export function pickDefaultKind(data: ChartPoint[]): ChartDisplayKind {
  const uniqueNames = new Set(data.map((d) => d.name));
  const allNonNegative = data.every((d) => Number.isFinite(d.value) && d.value >= 0);

  // Small categorical shares → pie; longer series → line; otherwise bar.
  if (
    uniqueNames.size >= 2 &&
    uniqueNames.size <= PIE_MAX_CATEGORIES &&
    data.length <= PIE_MAX_CATEGORIES &&
    allNonNegative
  ) {
    return "pie";
  }
  if (data.length >= LINE_MIN_ROWS) return "line";
  return "bar";
}

/**
 * Heuristic: first non-numeric-looking column as category, first numeric as value.
 * Returns none when the result set is not chartable.
 */
export function deriveChart(
  columns: string[],
  rows: Record<string, unknown>[],
): ChartSeries {
  if (!columns.length || rows.length < 1 || rows.length > MAX_CHART_ROWS) {
    return EMPTY_SERIES;
  }

  const sample = rows.slice(0, Math.min(rows.length, 12));
  const numericCols = columns.filter((col) =>
    sample.every((row) => row[col] == null || isNumeric(row[col])),
  );
  const categoryCols = columns.filter((col) => !numericCols.includes(col));

  if (!numericCols.length || !categoryCols.length) {
    return EMPTY_SERIES;
  }

  const categoryKey = categoryCols[0];
  const valueKey = numericCols[0];
  const data: ChartPoint[] = rows.map((row) => ({
    name: String(row[categoryKey] ?? "—"),
    value: toNumber(row[valueKey] ?? 0),
  }));

  const uniqueNames = new Set(data.map((d) => d.name));
  if (uniqueNames.size < 2) {
    return EMPTY_SERIES;
  }

  return {
    kind: pickDefaultKind(data),
    categoryKey,
    valueKey,
    data,
  };
}

/** Stable id so UI state resets when the underlying series changes. */
export function chartSeriesIdentity(series: ChartSeries): string {
  if (series.kind === "none") return "none";
  const points = series.data.map((d) => `${d.name}:${d.value}`).join("|");
  return `${series.kind}|${series.categoryKey}|${series.valueKey}|${points}`;
}

export function formatCell(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? value.toLocaleString()
      : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
