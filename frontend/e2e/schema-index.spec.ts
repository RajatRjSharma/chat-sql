import { expect, test } from "@playwright/test";
import { DEMO_SOURCE_ID, demoSource, embedResponse } from "./fixtures/api";
import { clearWorkspace, mockApi, seedWorkspace } from "./helpers/api";

test.describe("Schema index refresh", () => {
  test.beforeEach(async ({ page }) => {
    await clearWorkspace(page);
  });

  test("Evidence panel refreshes schema index and updates chunk count", async ({
    page,
  }) => {
    let embedCalls = 0;

    await mockApi(page, {
      sources: [demoSource],
      sessions: [],
    });

    await page.route("**/api/data/embed-schema", async (route) => {
      embedCalls += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...embedResponse,
          chunks_embedded: 12,
          tables_indexed: 12,
          previous_chunks: 3,
          indexed_at: "2026-08-05T15:30:00.000Z",
        }),
      });
    });

    await seedWorkspace(page, {
      dataSourceId: DEMO_SOURCE_ID,
      dataSourceName: "Demo Sales Warehouse",
      sessionId: null,
      chunksEmbedded: 3,
      tablesIndexed: 3,
      schemaIndexedAt: "2026-08-05T12:00:00.000Z",
    });

    page.on("dialog", (dialog) => dialog.accept());

    await page.goto("/");

    await expect(page.getByText("Evidence panel")).toBeVisible();
    await expect(page.getByText(/3 chunks/)).toBeVisible();

    await page.getByRole("button", { name: "Refresh schema index" }).click();

    await expect(page.getByText(/12 chunks/)).toBeVisible();
    await expect(page.getByText(/3 → 12 chunks/)).toBeVisible();
    expect(embedCalls).toBe(1);
  });
});
