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

/** Hard caps so charts stay readable from hundreds → millions of input rows. */
const MAX_CHART_POINTS = 40;
const MAX_SERIES_KEYS = 8;
const MAX_HEAT_DIM = 20;
const MAX_SCATTER_POINTS = 200;
const PIE_MAX_CATEGORIES = 8;
const LINE_MIN_ROWS = 8;
/** Multi-series can default to line with fewer periods than classic single series. */
const MULTI_LINE_MIN_ROWS = 4;
/** Skip text columns whose typical values would crush axis labels (e.g. STRING_AGG dumps). */
const MAX_AVG_CATEGORY_LABEL_LEN = 48;
/** Rows used to infer numeric vs categorical columns. */
const TYPE_SAMPLE_SIZE = 64;
/** Stop discovering new category labels (cardinality probe). */
const UNIQUE_LABEL_CAP = MAX_HEAT_DIM * 4;
/** Max rows scanned when aggregating into a capped chart (guards huge dumps). */
const MAX_ROW_SCAN = 50_000;

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

/** Evenly spaced sample — representative without scanning millions of rows. */
function sampleRows(
  rows: Record<string, unknown>[],
  size: number,
): Record<string, unknown>[] {
  if (rows.length <= size) return rows;
  const out: Record<string, unknown>[] = [];
  const step = rows.length / size;
  for (let i = 0; i < size; i += 1) {
    out.push(rows[Math.min(rows.length - 1, Math.floor(i * step))]);
  }
  return out;
}

function scanLimit(rowCount: number): number {
  return Math.min(rowCount, MAX_ROW_SCAN);
}

function averageLabelLength(
  rows: Record<string, unknown>[],
  column: string,
): number {
  const sample = sampleRows(rows, Math.min(TYPE_SAMPLE_SIZE, rows.length));
  if (!sample.length) return 0;
  let total = 0;
  for (const row of sample) {
    total += String(row[column] ?? "").length;
  }
  return total / sample.length;
}

/** Prefer short categorical labels over blob columns (STRING_AGG dumps). */
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
  maxUnique = UNIQUE_LABEL_CAP,
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  const limit = scanLimit(rows.length);
  for (let i = 0; i < limit; i += 1) {
    const name = labelOf(rows[i][column], "—");
    if (!seen.has(name)) {
      seen.add(name);
      out.push(name);
      if (out.length >= maxUnique) break;
    }
  }
  return out;
}

function uniqueCount(
  rows: Record<string, unknown>[],
  column: string,
  maxUnique = UNIQUE_LABEL_CAP,
): number {
  return uniqueLabels(rows, column, maxUnique).length;
}

/** True when labels look like a time / ordered sequence (line chart). */
export function looksTemporalLabels(
  names: string[],
  options?: { minRows?: number },
): boolean {
  const minRows = options?.minRows ?? LINE_MIN_ROWS;
  if (names.length < minRows) return false;
  const sample = names.slice(0, Math.min(names.length, 16));
  let hits = 0;
  for (const raw of sample) {
    const name = raw.trim();
    // Also accept ISO timestamps: 2024-01-01T00:00:00
    const head = name.slice(0, 10);
    if (
      DATE_RE.test(name) ||
      DATE_RE.test(head) ||
      YEAR_RE.test(name) ||
      MONTH_RE.test(name) ||
      QUARTER_RE.test(name)
    ) {
      hits += 1;
    }
  }
  return hits / sample.length >= 0.6;
}

/** High-cardinality id-like labels (bad as a bar axis; good as scatter point labels). */
function isHighCardinalityLabel(
  rows: Record<string, unknown>[],
  column: string,
): boolean {
  const uniq = uniqueCount(rows, column);
  if (uniq < 8) return false;
  const probed = Math.min(rows.length, MAX_ROW_SCAN);
  return uniq >= 12 || uniq / Math.max(probed, 1) >= 0.45;
}

function aggregateHeatCells(
  rows: Record<string, unknown>[],
  rowKey: string,
  colKey: string,
  valueKey: string,
): HeatCell[] {
  const cellMap = new Map<string, number>();
  const limit = scanLimit(rows.length);
  for (let i = 0; i < limit; i += 1) {
    const row = rows[i];
    const r = labelOf(row[rowKey], "—");
    const c = labelOf(row[colKey], "—");
    const key = `${r}\0${c}`;
    cellMap.set(key, (cellMap.get(key) ?? 0) + toNumber(row[valueKey]));
  }
  const heatData: HeatCell[] = [];
  for (const [key, value] of cellMap) {
    const [r, c] = key.split("\0");
    heatData.push({ row: r, col: c, value });
  }
  return heatData;
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
  if (looksTemporalLabels(categoryLabels, { minRows: MULTI_LINE_MIN_ROWS })) {
    return "line";
  }
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

  const aTemporal = looksTemporalLabels(labelsA, { minRows: MULTI_LINE_MIN_ROWS });
  const bTemporal = looksTemporalLabels(labelsB, { minRows: MULTI_LINE_MIN_ROWS });

  let categoryKey: string;
  let seriesKey: string;
  let categoryLabels: string[];
  let seriesLabels: string[];

  // Shape rule: put the time axis on X when present (domain-agnostic).
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

  const minDim = Math.min(categoryLabels.length, seriesLabels.length);
  const maxDim = Math.max(categoryLabels.length, seriesLabels.length);
  const gridSize = categoryLabels.length * seriesLabels.length;
  const dimsFitHeat =
    minDim >= 3 &&
    maxDim >= 6 &&
    gridSize >= 24 &&
    categoryLabels.length <= MAX_HEAT_DIM &&
    seriesLabels.length <= MAX_HEAT_DIM;

  const categoryIsTemporal = looksTemporalLabels(categoryLabels, {
    minRows: MULTI_LINE_MIN_ROWS,
  });

  // Time × few series → multi-line (any measure). Dense cat×cat → heatmap.
  const preferMultiLine =
    categoryIsTemporal && seriesLabels.length <= MAX_SERIES_KEYS;

  const preferHeat =
    dimsFitHeat &&
    !preferMultiLine &&
    (seriesLabels.length > MAX_SERIES_KEYS || maxDim >= 8 || minDim >= 4);

  if (preferHeat) {
    return finishHeatmap(
      categoryKey,
      seriesKey,
      valueKey,
      categoryLabels,
      seriesLabels,
      aggregateHeatCells(rows, categoryKey, seriesKey, valueKey),
    );
  }

  if (
    seriesLabels.length > MAX_SERIES_KEYS ||
    categoryLabels.length > MAX_CHART_POINTS * 2
  ) {
    if (dimsFitHeat) {
      return finishHeatmap(
        categoryKey,
        seriesKey,
        valueKey,
        categoryLabels,
        seriesLabels,
        aggregateHeatCells(rows, categoryKey, seriesKey, valueKey),
      );
    }
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

  const limit = scanLimit(rows.length);
  for (let i = 0; i < limit; i += 1) {
    const row = rows[i];
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

  const xKey = numericCols[0];
  const yKey = numericCols[1];
  const sampled = sampleRows(rows, MAX_SCATTER_POINTS);

  // Pure numeric correlation.
  if (usableCategoryCols.length === 0) {
    const points: ScatterPoint[] = sampled.map((row, index) => ({
      x: toNumber(row[xKey]),
      y: toNumber(row[yKey]),
      label: `Row ${index + 1}`,
    }));
    return finishScatter(xKey, yKey, points);
  }

  // Optional id/label column + two measures. High cardinality ⇒ scatter, not bar.
  if (usableCategoryCols.length === 1) {
    const labelCol = usableCategoryCols[0];
    if (!isHighCardinalityLabel(rows, labelCol)) return null;

    const points: ScatterPoint[] = sampled.map((row, index) => ({
      x: toNumber(row[xKey]),
      y: toNumber(row[yKey]),
      label: labelOf(row[labelCol], `Row ${index + 1}`),
    }));
    return finishScatter(xKey, yKey, points, labelCol);
  }

  return null;
}

/**
 * Build a chart for any non-empty result set (schema-agnostic, size-safe).
 *
 * Decisions use result *shape* only (cardinalities, temporal labels, numeric
 * columns) — not domain vocabulary — so the same rules work for sales,
 * logistics, finance, IoT, etc., from dozens to millions of rows.
 *
 * Strategies (first match wins):
 * 1. Two categoricals + measure → multi-line / grouped / stacked / heatmap
 * 2. Two numerics (optional high-card label) → scatter
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

  const probe = sampleRows(rows, TYPE_SAMPLE_SIZE);
  const numericCols = columns.filter((col) =>
    probe.every((row) => row[col] == null || row[col] === "" || isNumeric(row[col])),
  );
  const categoryCols = columns.filter((col) => !numericCols.includes(col));
  const usableCategoryCols = shortCategoryColumns(categoryCols, probe);

  const multi = tryMultiOrHeat(rows, usableCategoryCols, numericCols);
  if (multi && multi.kind !== "none") return multi;

  const scatter = tryScatter(rows, usableCategoryCols, numericCols);
  if (scatter && scatter.kind !== "none") return scatter;

  // Classic: short label + value (cap points for huge dumps)
  if (numericCols.length && usableCategoryCols.length) {
    const categoryKey = usableCategoryCols[0];
    const valueKey = numericCols[0];
    const limit = Math.min(rows.length, MAX_CHART_POINTS);
    const data = rows.slice(0, limit).map((row, index) => ({
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
    const limit = Math.min(rows.length, MAX_CHART_POINTS);
    const data = rows.slice(0, limit).map((row, index) => ({
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

  // Text-only: frequency of the first column (capped)
  const categoryKey = columns[0];
  const counts = new Map<string, number>();
  const limit = scanLimit(rows.length);
  for (let i = 0; i < limit; i += 1) {
    const name = labelOf(rows[i][categoryKey], "—");
    counts.set(name, (counts.get(name) ?? 0) + 1);
    if (counts.size > MAX_CHART_POINTS * 4) break;
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
