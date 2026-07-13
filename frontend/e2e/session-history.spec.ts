import { expect, test } from "@playwright/test";
import {
  DEMO_SOURCE_ID,
  SESSION_A_ID,
  demoSource,
  sessionSummaries,
} from "./fixtures/api";
import { clearWorkspace, mockApi, seedWorkspace } from "./helpers/api";

test.describe("Session history", () => {
  test.beforeEach(async ({ page }) => {
    await clearWorkspace(page);
    await seedWorkspace(page, {
      dataSourceId: DEMO_SOURCE_ID,
      dataSourceName: demoSource.name,
      sessionId: null,
      chunksEmbedded: 3,
    });
  });

  test("lists history and loads a full session", async ({ page }) => {
    await mockApi(page, {
      sources: [demoSource],
      sessions: sessionSummaries,
    });
    await page.goto("/");

    await expect(page.getByText("History")).toBeVisible();
    await expect(
      page.getByRole("button", { name: /What were total sales by region/i }).first(),
    ).toBeVisible();

    await page
      .getByRole("button", { name: /Which products sold the most units/i })
      .first()
      .click();

    await expect(
      page.getByText("Wireless Mouse topped unit sales.").first(),
    ).toBeVisible();
    await expect(page.getByText("Wireless Mouse", { exact: true }).first()).toBeVisible();
    await expect(page.getByText(/session bbbbbbbb/i)).toBeVisible();
  });

  test("new chat clears turns and allows a fresh session", async ({ page }) => {
    await mockApi(page, {
      sources: [demoSource],
      sessions: sessionSummaries,
    });
    await page.goto("/");

    await page
      .getByRole("button", { name: /What were total sales by region/i })
      .first()
      .click();
    await expect(
      page.getByText("East leads with the highest sales total.").first(),
    ).toBeVisible();

    await page.getByRole("button", { name: "New", exact: true }).click();

    await expect(page.getByText("Ask anything about the warehouse")).toBeVisible();
    await expect(page.getByText("East leads with the highest sales total.")).toHaveCount(0);
    await expect(page.getByText("new chat", { exact: true })).toBeVisible();
  });

  test("restores persisted session on reload", async ({ page }) => {
    await clearWorkspace(page);
    await seedWorkspace(page, {
      dataSourceId: DEMO_SOURCE_ID,
      dataSourceName: demoSource.name,
      sessionId: SESSION_A_ID,
      chunksEmbedded: 3,
    });
    await mockApi(page, {
      sources: [demoSource],
      sessions: sessionSummaries,
    });

    await page.goto("/");

    await expect(
      page.getByText("East leads with the highest sales total.").first(),
    ).toBeVisible();
    await expect(page.getByText(/session aaaaaaaa/i)).toBeVisible();
  });
});
