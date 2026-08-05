import { describe, expect, it } from "vitest";
import { deriveChart, pickDefaultKind } from "@/lib/chart";

describe("deriveChart", () => {
  it("builds a category + value series and defaults to pie for small shares", () => {
    const series = deriveChart(
      ["region", "revenue"],
      [
        { region: "North", revenue: 10 },
        { region: "South", revenue: 20 },
        { region: "East", revenue: 5 },
      ],
    );
    expect(series.kind).toBe("pie");
    expect(series.categoryKey).toBe("region");
    expect(series.valueKey).toBe("revenue");
    expect(series.data).toHaveLength(3);
  });

  it("charts a single-row metric as named points", () => {
    const series = deriveChart(["total_sales", "orders"], [{ total_sales: 100, orders: 4 }]);
    expect(series.kind).not.toBe("none");
    expect(series.data.map((d) => d.name)).toEqual(["total_sales", "orders"]);
    expect(series.data.map((d) => d.value)).toEqual([100, 4]);
  });

  it("ignores long text dumps as category and charts numeric metrics", () => {
    const sampleNames =
      "Initech, Wayne Enterprises, Massive Dynamic, Octan Corp, Oscorp, " +
      "Acme Corp, Stark Industries, Pied Piper, Gringotts, Aperture Science";
    const series = deriveChart(
      ["total_customers", "distinct_regions", "sample_names"],
      [
        {
          total_customers: 20,
          distinct_regions: 4,
          sample_names: sampleNames,
        },
      ],
    );
    expect(series.categoryKey).toBe("metric");
    expect(series.data.map((d) => d.name)).toEqual([
      "total_customers",
      "distinct_regions",
    ]);
    expect(series.data.map((d) => d.value)).toEqual([20, 4]);
  });

  it("uses frequency counts for text-only results", () => {
    const series = deriveChart(
      ["status"],
      [{ status: "open" }, { status: "open" }, { status: "closed" }],
    );
    expect(series.valueKey).toBe("count");
    expect(series.data.find((d) => d.name === "open")?.value).toBe(2);
    expect(series.data.find((d) => d.name === "closed")?.value).toBe(1);
  });

  it("returns none for empty input", () => {
    expect(deriveChart([], []).kind).toBe("none");
  });
});

describe("pickDefaultKind", () => {
  it("prefers pie for small non-negative shares", () => {
    const data = [
      { name: "North", value: 10 },
      { name: "South", value: 20 },
      { name: "East", value: 5 },
    ];
    expect(pickDefaultKind(data)).toBe("pie");
  });

  it("prefers bar for long categorical rankings (not line)", () => {
    const data = Array.from({ length: 20 }, (_, i) => ({
      name: `table_${i}`,
      value: 100 - i,
    }));
    expect(pickDefaultKind(data)).toBe("bar");
  });

  it("prefers line for time-like labels", () => {
    const data = Array.from({ length: 12 }, (_, i) => ({
      name: `2024-${String(i + 1).padStart(2, "0")}-01`,
      value: i + 1,
    }));
    expect(pickDefaultKind(data)).toBe("line");
  });
});
