import { expect, test } from "@playwright/test";
import { clearWorkspace, mockApi } from "./helpers/api";

test.describe("Connect warehouse", () => {
  test.beforeEach(async ({ page }) => {
    await clearWorkspace(page);
  });

  test("connects demo warehouse and opens workspace", async ({ page }) => {
    await mockApi(page, { sources: [] });
    await page.goto("/");

    await expect(page.getByRole("button", { name: "Connect & index" })).toBeVisible();
    await expect(page.getByText("Saved warehouses")).toHaveCount(0);

    await page.getByRole("button", { name: "Connect & index" }).click();

    await expect(page.getByRole("button", { name: "Switch warehouse" })).toBeVisible();
    await expect(page.getByText("Ask anything about the warehouse")).toBeVisible();
    await expect(
      page.getByText("Demo Sales Warehouse", { exact: true }).first(),
    ).toBeVisible();
  });

  test("shows connect error and stays on connect screen", async ({ page }) => {
    await mockApi(page, { sources: [], connectStatus: 502 });
    await page.goto("/");

    await page.getByRole("button", { name: "Connect & index" }).click();

    await expect(
      page.getByRole("alert").filter({ hasText: /mocked failure|Could not connect/i }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Connect & index" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Switch warehouse" })).toHaveCount(0);
  });
});
