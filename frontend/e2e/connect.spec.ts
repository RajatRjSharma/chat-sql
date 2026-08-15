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
    await expect(page.getByText("Evidence panel")).toBeVisible();
    await expect(page.getByText("Demo Sales Warehouse", { exact: true })).toBeVisible();
    // Connection provenance is available immediately (no chat required).
    await expect(page.getByText("Engine")).toBeVisible();
    await expect(page.getByText(/PostgreSQL · postgres/)).toBeVisible();
    await expect(page.getByText("read-only SELECT")).toBeVisible();
  });

  test("opens mobile evidence in a scrollable sheet", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockApi(page, { sources: [] });
    await page.goto("/");

    await page.getByRole("button", { name: "Connect & index" }).click();
    await expect(page.getByRole("textbox", { name: "Analytics question" })).toBeVisible();

    await page.getByRole("button", { name: "Session evidence" }).click();

    const sheet = page.getByRole("dialog", { name: "Session evidence" });
    await expect(sheet).toBeVisible();
    await expect(page.getByTestId("mobile-evidence-scroll")).toHaveCSS(
      "overflow-y",
      "auto",
    );

    const sheetBox = await sheet.boundingBox();
    expect(sheetBox?.height).toBeGreaterThan(700);

    await page.getByRole("button", { name: "Close session evidence" }).last().click();
    await expect(sheet).toBeHidden();
    await expect(page.getByRole("textbox", { name: "Analytics question" })).toBeVisible();
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
