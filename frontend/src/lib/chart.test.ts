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
  it("prefers line for long series", () => {
    const data = Array.from({ length: 13 }, (_, i) => ({
      name: `D${i}`,
      value: i + 1,
    }));
    expect(pickDefaultKind(data)).toBe("line");
  });
});
