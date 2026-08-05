export type ChartKind =
  | "bar"
  | "line"
  | "pie"
  | "grouped"
  | "stacked"
  | "scatter"
  | "heatmap"
  | "none";

export type ChartDisplayKind = Exclude<ChartKind, "none">;

/** How the result shape should be visualized (controls available toggles). */
export type ChartFamily = "single" | "multi" | "scatter" | "heatmap";

export type ChartPoint = { name: string; value: number };

export type ScatterPoint = { x: number; y: number; label?: string };

export type HeatCell = { row: string; col: string; value: number };

/** One x-axis category with a value per series key. */
export type MultiSeriesRow = { name: string } & Record<string, string | number>;

export type ChartSeries = {
  kind: ChartKind;
  family: ChartFamily;
  categoryKey: string;
  valueKey: string;
  /** Classic / aggregate points (also category totals for multi). */
  data: ChartPoint[];
  /** Second categorical column (series / color / heatmap column). */
  seriesKey?: string;
  seriesKeys?: string[];
  multiData?: MultiSeriesRow[];
  xKey?: string;
  yKey?: string;
  scatterData?: ScatterPoint[];
  rowKey?: string;
  colKey?: string;
  heatRows?: string[];
  heatCols?: string[];
  heatData?: HeatCell[];
};

const EMPTY_SERIES: ChartSeries = {
  kind: "none",
  family: "single",
  categoryKey: "",
  valueKey: "",
  data: [],
};

/** Hard cap so charts stay readable; excess rows are truncated (top / first). */
const MAX_CHART_POINTS = 40;
const MAX_SERIES_KEYS = 8;
const MAX_HEAT_DIM = 20;
const MAX_SCATTER_POINTS = 200;
const PIE_MAX_CATEGORIES = 8;
const LINE_MIN_ROWS = 8;
/** Skip text columns whose typical values would crush axis labels (e.g. STRING_AGG dumps). */
const MAX_AVG_CATEGORY_LABEL_LEN = 48;

const MONTH_RE =
  /^(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*(\s|-|_|\/|\.|'|\d|$)/i;
const DATE_RE =
  /^\d{4}([-/.]\d{1,2}){1,2}$|^\d{1,2}([-/.]\d{1,2})([-/.]\d{2,4})$/;
const YEAR_RE = /^(19|20)\d{2}$/;
const QUARTER_RE = /^q[1-4]([-'’]?\s?\d{2,4})?$/i;

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

function averageLabelLength(
  rows: Record<string, unknown>[],
  column: string,
): number {
  if (!rows.length) return 0;
  let total = 0;
  for (const row of rows) {
    total += String(row[column] ?? "").length;
  }
  return total / rows.length;
}

/** Prefer short categorical labels (region, status) over blob columns (sample_names). */
function shortCategoryColumns(
  columns: string[],
  rows: Record<string, unknown>[],
): string[] {
  return columns.filter(
    (col) => averageLabelLength(rows, col) <= MAX_AVG_CATEGORY_LABEL_LEN,
  );
}

function uniqueLabels(
  rows: Record<string, unknown>[],
  column: string,
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const row of rows) {
    const name = labelOf(row[column], "—");
    if (!seen.has(name)) {
      seen.add(name);
      out.push(name);
    }
  }
  return out;
}

/** True when labels look like a time / ordered sequence (line chart). */
export function looksTemporalLabels(names: string[]): boolean {
  if (names.length < LINE_MIN_ROWS) return false;
  const sample = names.slice(0, Math.min(names.length, 16));
  let hits = 0;
  for (const raw of sample) {
    const name = raw.trim();
    if (
      DATE_RE.test(name) ||
      YEAR_RE.test(name) ||
      MONTH_RE.test(name) ||
      QUARTER_RE.test(name)
    ) {
      hits += 1;
    }
  }
  return hits / sample.length >= 0.6;
}

/**
 * Pick the default visualization from a classic 2D series.
 * User can still switch Bar / Line / Pie in the UI.
 */
export function pickDefaultKind(data: ChartPoint[]): ChartDisplayKind {
  const uniqueNames = new Set(data.map((d) => d.name));
  const allNonNegative = data.every((d) => Number.isFinite(d.value) && d.value >= 0);

  if (
    uniqueNames.size >= 2 &&
    uniqueNames.size <= PIE_MAX_CATEGORIES &&
    data.length <= PIE_MAX_CATEGORIES &&
    allNonNegative
  ) {
    return "pie";
  }
  if (looksTemporalLabels(data.map((d) => d.name))) {
    return "line";
  }
  return "bar";
}

function pickMultiDefaultKind(
  categoryLabels: string[],
  seriesKeys: string[],
): Extract<ChartDisplayKind, "grouped" | "stacked" | "line"> {
  if (looksTemporalLabels(categoryLabels)) return "line";
  if (seriesKeys.length >= 3) return "stacked";
  return "grouped";
}

function finishSingle(
  categoryKey: string,
  valueKey: string,
  data: ChartPoint[],
): ChartSeries {
  const cleaned = data
    .map((d) => ({
      name: d.name.trim() ? d.name : "—",
      value: Number.isFinite(d.value) ? d.value : 0,
    }))
    .slice(0, MAX_CHART_POINTS);

  if (!cleaned.length) return EMPTY_SERIES;

  return {
    kind: pickDefaultKind(cleaned),
    family: "single",
    categoryKey,
    valueKey,
    data: cleaned,
  };
}

function finishMulti(
  categoryKey: string,
  seriesKey: string,
  valueKey: string,
  seriesKeys: string[],
  multiData: MultiSeriesRow[],
): ChartSeries {
  const keys = seriesKeys.slice(0, MAX_SERIES_KEYS);
  const rows = multiData.slice(0, MAX_CHART_POINTS).map((row) => {
    const next: MultiSeriesRow = { name: String(row.name).trim() || "—" };
    for (const key of keys) {
      next[key] = toNumber(row[key]);
    }
    return next;
  });
  if (!rows.length || !keys.length) return EMPTY_SERIES;

  const data: ChartPoint[] = rows.map((row) => ({
    name: String(row.name),
    value: keys.reduce((sum, key) => sum + toNumber(row[key]), 0),
  }));

  return {
    kind: pickMultiDefaultKind(
      rows.map((r) => String(r.name)),
      keys,
    ),
    family: "multi",
    categoryKey,
    valueKey,
    seriesKey,
    seriesKeys: keys,
    multiData: rows,
    data,
  };
}

function finishScatter(
  xKey: string,
  yKey: string,
  points: ScatterPoint[],
  labelKey?: string,
): ChartSeries {
  const cleaned = points
    .filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y))
    .slice(0, MAX_SCATTER_POINTS);
  if (cleaned.length < 2) return EMPTY_SERIES;

  return {
    kind: "scatter",
    family: "scatter",
    categoryKey: labelKey ?? "point",
    valueKey: yKey,
    xKey,
    yKey,
    scatterData: cleaned,
    data: cleaned.map((p, i) => ({
      name: p.label?.trim() || `P${i + 1}`,
      value: p.y,
    })),
  };
}

function finishHeatmap(
  rowKey: string,
  colKey: string,
  valueKey: string,
  heatRows: string[],
  heatCols: string[],
  heatData: HeatCell[],
): ChartSeries {
  const rows = heatRows.slice(0, MAX_HEAT_DIM);
  const cols = heatCols.slice(0, MAX_HEAT_DIM);
  const rowSet = new Set(rows);
  const colSet = new Set(cols);
  const cells = heatData.filter((c) => rowSet.has(c.row) && colSet.has(c.col));
  if (!rows.length || !cols.length || !cells.length) return EMPTY_SERIES;

  return {
    kind: "heatmap",
    family: "heatmap",
    categoryKey: rowKey,
    valueKey,
    seriesKey: colKey,
    rowKey,
    colKey,
    heatRows: rows,
    heatCols: cols,
    heatData: cells,
    data: cells.map((c) => ({
      name: `${c.row} × ${c.col}`,
      value: c.value,
    })),
  };
}

function tryMultiOrHeat(
  rows: Record<string, unknown>[],
  usableCategoryCols: string[],
  numericCols: string[],
): ChartSeries | null {
  if (usableCategoryCols.length < 2 || !numericCols.length) return null;

  const catA = usableCategoryCols[0];
  const catB = usableCategoryCols[1];
  const valueKey = numericCols[0];
  const labelsA = uniqueLabels(rows, catA);
  const labelsB = uniqueLabels(rows, catB);
  if (labelsA.length < 2 || labelsB.length < 2) return null;

  const aTemporal = looksTemporalLabels(labelsA);
  const bTemporal = looksTemporalLabels(labelsB);

  let categoryKey: string;
  let seriesKey: string;
  let categoryLabels: string[];
  let seriesLabels: string[];

  if (aTemporal && !bTemporal) {
    categoryKey = catA;
    seriesKey = catB;
    categoryLabels = labelsA;
    seriesLabels = labelsB;
  } else if (bTemporal && !aTemporal) {
    categoryKey = catB;
    seriesKey = catA;
    categoryLabels = labelsB;
    seriesLabels = labelsA;
  } else if (labelsA.length >= labelsB.length) {
    categoryKey = catA;
    seriesKey = catB;
    categoryLabels = labelsA;
    seriesLabels = labelsB;
  } else {
    categoryKey = catB;
    seriesKey = catA;
    categoryLabels = labelsB;
    seriesLabels = labelsA;
  }

  const preferHeat =
    categoryLabels.length >= 3 &&
    seriesLabels.length >= 3 &&
    categoryLabels.length <= MAX_HEAT_DIM &&
    seriesLabels.length <= MAX_HEAT_DIM &&
    (seriesLabels.length > MAX_SERIES_KEYS ||
      (categoryLabels.length >= 6 && seriesLabels.length >= 6));

  if (preferHeat) {
    const cellMap = new Map<string, number>();
    for (const row of rows) {
      const r = labelOf(row[categoryKey], "—");
      const c = labelOf(row[seriesKey], "—");
      const key = `${r}\0${c}`;
      cellMap.set(key, (cellMap.get(key) ?? 0) + toNumber(row[valueKey]));
    }
    const heatData: HeatCell[] = [];
    for (const [key, value] of cellMap) {
      const [r, c] = key.split("\0");
      heatData.push({ row: r, col: c, value });
    }
    return finishHeatmap(
      categoryKey,
      seriesKey,
      valueKey,
      categoryLabels,
      seriesLabels,
      heatData,
    );
  }

  if (
    seriesLabels.length > MAX_SERIES_KEYS ||
    categoryLabels.length > MAX_CHART_POINTS * 2
  ) {
    return null;
  }

  const seriesKeys = seriesLabels.slice(0, MAX_SERIES_KEYS);
  const categories = categoryLabels.slice(0, MAX_CHART_POINTS);
  const catSet = new Set(categories);
  const keySet = new Set(seriesKeys);
  const pivot = new Map<string, MultiSeriesRow>();

  for (const name of categories) {
    const row: MultiSeriesRow = { name };
    for (const key of seriesKeys) row[key] = 0;
    pivot.set(name, row);
  }

  for (const row of rows) {
    const cat = labelOf(row[categoryKey], "—");
    const series = labelOf(row[seriesKey], "—");
    if (!catSet.has(cat) || !keySet.has(series)) continue;
    const bucket = pivot.get(cat);
    if (!bucket) continue;
    bucket[series] = toNumber(bucket[series]) + toNumber(row[valueKey]);
  }

  return finishMulti(
    categoryKey,
    seriesKey,
    valueKey,
    seriesKeys,
    categories.map((name) => pivot.get(name)!),
  );
}

function tryScatter(
  rows: Record<string, unknown>[],
  usableCategoryCols: string[],
  numericCols: string[],
): ChartSeries | null {
  if (numericCols.length < 2 || rows.length < 5) return null;
  // Correlation / measure-vs-measure: only when there is no categorical axis.
  if (usableCategoryCols.length > 0) return null;

  const xKey = numericCols[0];
  const yKey = numericCols[1];
  const points: ScatterPoint[] = rows.map((row, index) => ({
    x: toNumber(row[xKey]),
    y: toNumber(row[yKey]),
    label: `Row ${index + 1}`,
  }));
  return finishScatter(xKey, yKey, points);
}

/**
 * Build a chart for any non-empty result set.
 *
 * Strategies (first match wins):
 * 1. Two categoricals + measure → grouped/stacked/multi-line or heatmap
 * 2. Two numerics, no category → scatter
 * 3. Category + numeric (classic series)
 * 4. Single row metrics → one bar per numeric column
 * 5. Multi-row all-numeric → row labels + first numeric
 * 6. Text-only → frequency counts
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
  const usableCategoryCols = shortCategoryColumns(categoryCols, sample);

  const multi = tryMultiOrHeat(rows, usableCategoryCols, numericCols);
  if (multi && multi.kind !== "none") return multi;

  const scatter = tryScatter(rows, usableCategoryCols, numericCols);
  if (scatter && scatter.kind !== "none") return scatter;

  // Classic: short label + value
  if (numericCols.length && usableCategoryCols.length) {
    const categoryKey = usableCategoryCols[0];
    const valueKey = numericCols[0];
    const data = rows.map((row, index) => ({
      name: labelOf(row[categoryKey], `Row ${index + 1}`),
      value: toNumber(row[valueKey]),
    }));
    return finishSingle(categoryKey, valueKey, data);
  }

  // Single row of metrics
  if (numericCols.length && rows.length === 1) {
    const row = rows[0];
    const data = numericCols.map((col) => ({
      name: col,
      value: toNumber(row[col]),
    }));
    return finishSingle("metric", "value", data);
  }

  // Multi-row numeric-only (or long-only text cats)
  if (numericCols.length) {
    const labelCol =
      usableCategoryCols[0] ??
      (categoryCols.length === 0 ? columns[0] : null);
    const valueKey =
      (labelCol && numericCols.find((c) => c !== labelCol)) ?? numericCols[0];
    const data = rows.map((row, index) => ({
      name:
        labelCol && labelCol !== valueKey
          ? labelOf(row[labelCol], `Row ${index + 1}`)
          : `Row ${index + 1}`,
      value: toNumber(row[valueKey]),
    }));
    return finishSingle(
      labelCol && labelCol !== valueKey ? labelCol : "row",
      valueKey,
      data,
    );
  }

  // Text-only: frequency of the first column
  const categoryKey = columns[0];
  const counts = new Map<string, number>();
  for (const row of rows) {
    const name = labelOf(row[categoryKey], "—");
    counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  const data = [...counts.entries()]
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value || a.name.localeCompare(b.name));

  return finishSingle(categoryKey, "count", data);
}

/** Stable id so UI state resets when the underlying series changes. */
export function chartSeriesIdentity(series: ChartSeries): string {
  if (series.kind === "none") return "none";
  if (series.family === "multi") {
    const keyList = series.seriesKeys ?? [];
    const rows = (series.multiData ?? [])
      .map((r) => `${r.name}:${keyList.map((k) => r[k]).join(",")}`)
      .join("|");
    return `multi|${series.kind}|${series.categoryKey}|${series.seriesKey}|${series.valueKey}|${keyList.join(",")}|${rows}`;
  }
  if (series.family === "scatter") {
    const pts = (series.scatterData ?? [])
      .map((p) => `${p.x},${p.y}`)
      .join("|");
    return `scatter|${series.xKey}|${series.yKey}|${pts}`;
  }
  if (series.family === "heatmap") {
    const cells = (series.heatData ?? [])
      .map((c) => `${c.row}x${c.col}:${c.value}`)
      .join("|");
    return `heat|${series.rowKey}|${series.colKey}|${series.valueKey}|${cells}`;
  }
  const points = series.data.map((d) => `${d.name}:${d.value}`).join("|");
  return `${series.kind}|${series.categoryKey}|${series.valueKey}|${points}`;
}

/** Axis subtitle under “Visualization”. */
export function chartAxisLabel(series: ChartSeries): string {
  if (series.family === "multi" && series.seriesKey) {
    return `${series.valueKey} · ${series.categoryKey} × ${series.seriesKey}`;
  }
  if (series.family === "scatter" && series.xKey && series.yKey) {
    return `${series.yKey} vs ${series.xKey}`;
  }
  if (series.family === "heatmap" && series.rowKey && series.colKey) {
    return `${series.valueKey} · ${series.rowKey} × ${series.colKey}`;
  }
  return `${series.valueKey} · ${series.categoryKey}`;
}

/** Points / categories shown (for truncation notes). */
export function chartVisibleCount(series: ChartSeries): number {
  if (series.family === "multi") return series.multiData?.length ?? 0;
  if (series.family === "scatter") return series.scatterData?.length ?? 0;
  if (series.family === "heatmap") return series.heatData?.length ?? 0;
  return series.data.length;
}

/** Toggle options for this result shape. */
export function availableChartKinds(series: ChartSeries): ChartDisplayKind[] {
  switch (series.family) {
    case "multi":
      return ["grouped", "stacked", "line"];
    case "scatter":
      return ["scatter"];
    case "heatmap":
      return ["heatmap"];
    default:
      return ["bar", "line", "pie"];
  }
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
