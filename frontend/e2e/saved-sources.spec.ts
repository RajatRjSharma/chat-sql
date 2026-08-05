import { expect, test } from "@playwright/test";
import {
  demoSource,
  demoSourceNeedsEmbed,
} from "./fixtures/api";
import { clearWorkspace, mockApi } from "./helpers/api";

test.describe("Saved warehouses", () => {
  test.beforeEach(async ({ page }) => {
    await clearWorkspace(page);
  });

  test("lists saved sources and opens one into workspace", async ({ page }) => {
    await mockApi(page, {
      sources: [demoSource],
      sessions: [],
    });
    await page.goto("/");

    await expect(page.getByText("Saved warehouses")).toBeVisible();
    await page.getByRole("button", { name: /^Demo Sales Warehouse/ }).click();

    await expect(page.getByRole("button", { name: "Switch warehouse" })).toBeVisible();
    await expect(page.getByText("History")).toBeVisible();
    await expect(page.getByText("Evidence panel")).toBeVisible();
    await expect(page.getByText("Demo Sales Warehouse", { exact: true })).toBeVisible();
  });

  test("re-embeds when selected source has zero chunks", async ({ page }) => {
    let embedCalled = false;

    await mockApi(page, {
      sources: [demoSourceNeedsEmbed],
      sessions: [],
    });

    // Override after catch-all so this handler wins (LIFO).
    await page.route("**/api/data/embed-schema", async (route) => {
      embedCalled = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data_source_id: demoSourceNeedsEmbed.id,
          chunks_embedded: 2,
          tables_indexed: 2,
          previous_chunks: 0,
          indexed_at: "2026-08-05T12:00:00.000Z",
          status: "ok",
        }),
      });
    });

    await page.goto("/");
    await page.getByRole("button", { name: /^Unindexed Warehouse/ }).click();

    await expect(page.getByRole("button", { name: "Switch warehouse" })).toBeVisible();
    expect(embedCalled).toBe(true);
  });

  test("switch warehouse returns to picker with saved sources", async ({ page }) => {
    await mockApi(page, {
      sources: [demoSource],
      sessions: [],
    });
    await page.goto("/");
    await page.getByRole("button", { name: /^Demo Sales Warehouse/ }).click();
    await expect(page.getByRole("button", { name: "Switch warehouse" })).toBeVisible();

    await page.getByRole("button", { name: "Switch warehouse" }).click();

    await expect(page.getByText("Saved warehouses")).toBeVisible();
    await expect(page.getByRole("button", { name: /^Demo Sales Warehouse/ })).toBeVisible();
    await expect(page.getByRole("button", { name: "Connect & index" })).toBeVisible();
  });
});
