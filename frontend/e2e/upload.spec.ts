import { expect, test } from "@playwright/test";
import { clearWorkspace, mockApi } from "./helpers/api";

test.describe("Upload CSV / Excel", () => {
  test.beforeEach(async ({ page }) => {
    await clearWorkspace(page);
  });

  test("uploads a CSV and opens the workspace", async ({ page }) => {
    await mockApi(page, { sources: [] });
    await page.goto("/");

    await expect(page.getByText("Upload CSV / Excel")).toBeVisible();

    await page.getByPlaceholder("Q1 sales export").fill("Demo upload");
    await page
      .locator('input[type="file"]')
      .setInputFiles({
        name: "sales.csv",
        mimeType: "text/csv",
        buffer: Buffer.from("region,amount\nEast,100\nWest,50\n"),
      });

    await page.getByRole("button", { name: "Upload & index" }).click();

    await expect(page.getByText("Ask anything about the warehouse")).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText("sales (upload)", { exact: true }).first()).toBeVisible();
  });

  test("shows upload error and stays on connect screen", async ({ page }) => {
    await mockApi(page, { sources: [], uploadStatus: 400 });
    await page.goto("/");

    await page
      .locator('input[type="file"]')
      .setInputFiles({
        name: "notes.txt",
        mimeType: "text/plain",
        buffer: Buffer.from("hello"),
      });
    await page.getByRole("button", { name: "Upload & index" }).click();

    await expect(
      page.getByRole("alert").filter({ hasText: /Unsupported|Upload/i }),
    ).toBeVisible();
    await expect(page.getByText("Upload CSV / Excel")).toBeVisible();
  });
});
