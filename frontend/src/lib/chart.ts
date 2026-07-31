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

/** Hard cap so charts stay readable; excess rows are truncated (top / first). */
const MAX_CHART_POINTS = 40;
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
  if (value == null || value === "") return 0;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : 0;
}

function labelOf(value: unknown, fallback: string): string {
  if (value == null || value === "") return fallback;
  return String(value);
}

function finish(categoryKey: string, valueKey: string, data: ChartPoint[]): ChartSeries {
  const cleaned = data
    .map((d) => ({
      name: d.name.trim() ? d.name : "—",
      value: Number.isFinite(d.value) ? d.value : 0,
    }))
    .slice(0, MAX_CHART_POINTS);

  if (!cleaned.length) return EMPTY_SERIES;

  return {
    kind: pickDefaultKind(cleaned),
    categoryKey,
    valueKey,
    data: cleaned,
  };
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
 * Build a chart for any non-empty result set.
 *
 * Strategies (first match wins):
 * 1. Category column + numeric column (classic series; 1+ points OK)
 * 2. Single row, one or more metrics → one bar per numeric column
 * 3. Multi-row all-numeric → row labels + first numeric column
 * 4. Text-only → frequency counts for the first column
 */
export function deriveChart(
  columns: string[],
  rows: Record<string, unknown>[],
): ChartSeries {
  if (!columns.length || rows.length < 1) {
    return EMPTY_SERIES;
  }

  const sample = rows.slice(0, Math.min(rows.length, 12));
  const numericCols = columns.filter((col) =>
    sample.every((row) => row[col] == null || row[col] === "" || isNumeric(row[col])),
  );
  const categoryCols = columns.filter((col) => !numericCols.includes(col));

  // 1) Classic: label + value
  if (numericCols.length && categoryCols.length) {
    const categoryKey = categoryCols[0];
    const valueKey = numericCols[0];
    const data = rows.map((row, index) => ({
      name: labelOf(row[categoryKey], `Row ${index + 1}`),
      value: toNumber(row[valueKey]),
    }));
    return finish(categoryKey, valueKey, data);
  }

  // 2) Single row of metrics (e.g. SELECT SUM(...) AS total)
  if (numericCols.length && rows.length === 1) {
    const row = rows[0];
    const data = numericCols.map((col) => ({
      name: col,
      value: toNumber(row[col]),
    }));
    return finish("metric", "value", data);
  }

  // 3) Multi-row numeric-only: plot first numeric against row index / first col
  if (numericCols.length) {
    const labelCol = columns[0];
    const valueKey = numericCols.find((c) => c !== labelCol) ?? numericCols[0];
    const data = rows.map((row, index) => ({
      name:
        labelCol !== valueKey
          ? labelOf(row[labelCol], `Row ${index + 1}`)
          : `Row ${index + 1}`,
      value: toNumber(row[valueKey]),
    }));
    return finish(labelCol !== valueKey ? labelCol : "row", valueKey, data);
  }

  // 4) Text-only: frequency of the first column (top N)
  const categoryKey = columns[0];
  const counts = new Map<string, number>();
  for (const row of rows) {
    const name = labelOf(row[categoryKey], "—");
    counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  const data = [...counts.entries()]
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value || a.name.localeCompare(b.name));

  return finish(categoryKey, "count", data);
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
