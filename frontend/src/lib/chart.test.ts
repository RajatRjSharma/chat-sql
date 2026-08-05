import { describe, expect, it } from "vitest";
import {
  availableChartKinds,
  chartAxisLabel,
  deriveChart,
  pickDefaultKind,
} from "@/lib/chart";

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
    expect(series.family).toBe("single");
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

  it("pivots two categoricals + measure into a multi-series chart", () => {
    const series = deriveChart(
      ["region", "channel", "revenue"],
      [
        { region: "North", channel: "web", revenue: 10 },
        { region: "North", channel: "store", revenue: 5 },
        { region: "South", channel: "web", revenue: 20 },
        { region: "South", channel: "store", revenue: 8 },
      ],
    );
    expect(series.family).toBe("multi");
    expect(series.kind).toBe("grouped");
    expect(series.categoryKey).toBe("region");
    expect(series.seriesKey).toBe("channel");
    expect(series.seriesKeys).toEqual(["web", "store"]);
    expect(series.multiData).toHaveLength(2);
    expect(series.multiData?.[0]).toMatchObject({
      name: "North",
      web: 10,
      store: 5,
    });
    expect(availableChartKinds(series)).toEqual(["grouped", "stacked", "line"]);
    expect(chartAxisLabel(series)).toContain("region × channel");
  });

  it("defaults multi-series with 3+ keys to stacked", () => {
    const regions = ["North", "South", "East", "West"];
    const channels = ["web", "store", "partner"];
    const rows = regions.flatMap((region) =>
      channels.map((channel) => ({
        region,
        channel,
        revenue: region.length + channel.length,
      })),
    );
    const series = deriveChart(["region", "channel", "revenue"], rows);
    expect(series.family).toBe("multi");
    expect(series.categoryKey).toBe("region");
    expect(series.seriesKeys).toHaveLength(3);
    expect(series.kind).toBe("stacked");
  });

  it("defaults temporal multi-series to line", () => {
    const months = [
      "2024-01-01",
      "2024-02-01",
      "2024-03-01",
      "2024-04-01",
      "2024-05-01",
      "2024-06-01",
      "2024-07-01",
      "2024-08-01",
    ];
    const rows = months.flatMap((month) => [
      { month, segment: "A", revenue: 10 },
      { month, segment: "B", revenue: 7 },
    ]);
    const series = deriveChart(["month", "segment", "revenue"], rows);
    expect(series.family).toBe("multi");
    expect(series.kind).toBe("line");
    expect(series.categoryKey).toBe("month");
  });

  it("smoke: monthly measure by segment → multi-line (not heatmap)", () => {
    const months = Array.from({ length: 12 }, (_, i) => `2024-${String(i + 1).padStart(2, "0")}`);
    const segments = ["Consumer", "Enterprise", "SMB", "Startup"];
    const rows = months.flatMap((month) =>
      segments.map((segment) => ({
        month,
        segment,
        total_sales: 1000,
      })),
    );
    const series = deriveChart(["month", "segment", "total_sales"], rows);
    expect(series.family).toBe("multi");
    expect(series.kind).toBe("line");
    expect(series.categoryKey).toBe("month");
  });

  it("builds a heatmap for dense non-temporal category grids", () => {
    const sites = ["S1", "S2", "S3", "S4", "S5", "S6"];
    const products = ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"];
    const rows = sites.flatMap((site) =>
      products.map((product, i) => ({
        site,
        product,
        metric: site.length + i,
      })),
    );
    const series = deriveChart(["site", "product", "metric"], rows);
    expect(series.family).toBe("heatmap");
    expect(series.kind).toBe("heatmap");
    expect(
      new Set([...(series.heatRows ?? []), ...(series.heatCols ?? [])]).size,
    ).toBe(14);
    expect(availableChartKinds(series)).toEqual(["heatmap"]);
  });

  it("smoke: time × region counts → multi-line (shape rule, any domain)", () => {
    const regions = ["East", "North", "South", "West"];
    const months = Array.from({ length: 12 }, (_, i) =>
      `2024-${String(i + 1).padStart(2, "0")}`,
    );
    const rows = regions.flatMap((region) =>
      months.map((month, i) => ({
        region,
        month,
        order_count: 10 + i,
      })),
    );
    const series = deriveChart(["region", "month", "order_count"], rows);
    expect(series.family).toBe("multi");
    expect(series.kind).toBe("line");
    expect(series.categoryKey).toBe("month");
  });

  it("builds a scatter from two numeric columns", () => {
    const rows = Array.from({ length: 8 }, (_, i) => ({
      invoice_amount: 100 + i * 10,
      payment_amount: 90 + i * 9,
    }));
    const series = deriveChart(["invoice_amount", "payment_amount"], rows);
    expect(series.family).toBe("scatter");
    expect(series.kind).toBe("scatter");
    expect(series.xKey).toBe("invoice_amount");
    expect(series.yKey).toBe("payment_amount");
    expect(series.scatterData).toHaveLength(8);
    expect(chartAxisLabel(series)).toBe("payment_amount vs invoice_amount");
  });

  it("smoke: high-card label + two measures → scatter", () => {
    const rows = Array.from({ length: 20 }, (_, i) => ({
      record_id: `REC-${String(i + 1).padStart(6, "0")}`,
      measure_a: 100 + i * 5,
      measure_b: 90 + i * 5,
    }));
    const series = deriveChart(["record_id", "measure_a", "measure_b"], rows);
    expect(series.family).toBe("scatter");
    expect(series.kind).toBe("scatter");
    expect(series.xKey).toBe("measure_a");
    expect(series.yKey).toBe("measure_b");
    expect(availableChartKinds(series)).toEqual(["scatter"]);
  });

  it("smoke: two low-card dims + measure stays grouped/stacked multi", () => {
    const dimA = ["East", "North", "South", "West"];
    const dimB = ["Web", "Store", "Partner", "Phone", "Other"];
    const rows = dimA.flatMap((a) =>
      dimB.map((b) => ({
        dim_a: a,
        dim_b: b,
        metric: 1000,
      })),
    );
    const series = deriveChart(["dim_a", "dim_b", "metric"], rows);
    expect(series.family).toBe("multi");
    expect(["grouped", "stacked"]).toContain(series.kind);
    expect(series.kind).not.toBe("heatmap");
  });

  it("caps classic series for very large row dumps", () => {
    const rows = Array.from({ length: 5000 }, (_, i) => ({
      label: `row_${i}`,
      value: i,
    }));
    const series = deriveChart(["label", "value"], rows);
    expect(series.family).toBe("single");
    expect(series.data.length).toBeLessThanOrEqual(40);
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
