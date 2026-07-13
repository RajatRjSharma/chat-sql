export type ChartKind = "bar" | "line" | "none";

export type ChartSeries = {
  kind: ChartKind;
  categoryKey: string;
  valueKey: string;
  data: { name: string; value: number }[];
};

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

/**
 * Heuristic: first non-numeric-looking column as category, first numeric as value.
 * Returns none when the result set is not chartable.
 */
export function deriveChart(
  columns: string[],
  rows: Record<string, unknown>[],
): ChartSeries {
  if (!columns.length || rows.length < 1 || rows.length > 40) {
    return { kind: "none", categoryKey: "", valueKey: "", data: [] };
  }

  const sample = rows.slice(0, Math.min(rows.length, 12));
  const numericCols = columns.filter((col) =>
    sample.every((row) => row[col] == null || isNumeric(row[col])),
  );
  const categoryCols = columns.filter((col) => !numericCols.includes(col));

  if (!numericCols.length || !categoryCols.length) {
    return { kind: "none", categoryKey: "", valueKey: "", data: [] };
  }

  const categoryKey = categoryCols[0];
  const valueKey = numericCols[0];
  const data = rows.map((row) => ({
    name: String(row[categoryKey] ?? "—"),
    value: toNumber(row[valueKey] ?? 0),
  }));

  const uniqueNames = new Set(data.map((d) => d.name));
  if (uniqueNames.size < 2) {
    return { kind: "none", categoryKey: "", valueKey: "", data: [] };
  }

  return {
    kind: data.length > 12 ? "line" : "bar",
    categoryKey,
    valueKey,
    data,
  };
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
