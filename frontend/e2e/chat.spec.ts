import { expect, test } from "@playwright/test";
import { DEMO_SOURCE_ID, chatOkResponse, demoSource } from "./fixtures/api";
import { clearWorkspace, mockApi, seedWorkspace } from "./helpers/api";

test.describe("Chat workspace", () => {
  test.beforeEach(async ({ page }) => {
    await clearWorkspace(page);
    await seedWorkspace(page, {
      dataSourceId: DEMO_SOURCE_ID,
      dataSourceName: demoSource.name,
      sessionId: null,
      chunksEmbedded: 3,
    });
  });

  test("asks a question and shows answer, SQL, table, and chart", async ({ page }) => {
    await mockApi(page, {
      sources: [demoSource],
      sessions: [],
    });
    await page.goto("/");

    await expect(page.getByText("Ask anything about the warehouse")).toBeVisible();

    await page.getByLabel("Analytics question").fill(chatOkResponse.question);
    await page.getByRole("button", { name: "Ask", exact: true }).click();

    await expect(page.getByText(chatOkResponse.answer).first()).toBeVisible();
    await expect(page.getByText("East", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("42,000").or(page.getByText("42000")).first()).toBeVisible();

    await page.getByRole("button", { name: /Generated SQL/i }).click();
    await expect(page.locator("pre").filter({ hasText: /SELECT region/i })).toBeVisible();

    await expect(page.getByText("Visualization").first()).toBeVisible();
    await expect(page.getByText("Result set").first()).toBeVisible();
  });

  test("shows chat error without hanging on analyzing state", async ({ page }) => {
    await mockApi(page, {
      sources: [demoSource],
      sessions: [],
      chatStatus: 502,
    });
    await page.goto("/");

    await page.getByLabel("Analytics question").fill("broken question");
    await page.getByRole("button", { name: "Ask", exact: true }).click();

    await expect(
      page.getByRole("alert").filter({ hasText: /mocked upstream|AI provider/i }),
    ).toBeVisible();
    await expect(page.getByText("Analyzing…")).toHaveCount(0);
  });
});
