import { expect, test } from "@playwright/test";
import { DEMO_SOURCE_ID, demoSource } from "./fixtures/api";
import { clearWorkspace, mockApi, seedWorkspace } from "./helpers/api";

async function installFakeSpeechRecognition(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
    class FakeSpeechRecognition {
      continuous = false;
      interimResults = true;
      lang = "en-US";
      onresult: ((event: unknown) => void) | null = null;
      onerror: ((event: unknown) => void) | null = null;
      onend: (() => void) | null = null;

      start() {
        window.setTimeout(() => {
          this.onresult?.({
            resultIndex: 0,
            results: [
              {
                isFinal: false,
                0: { transcript: "sales by region" },
              },
            ],
          });
          this.onresult?.({
            resultIndex: 0,
            results: [
              {
                isFinal: true,
                0: { transcript: "What were total sales by region?" },
              },
            ],
          });
          this.onend?.();
        }, 40);
      }

      stop() {
        this.onend?.();
      }

      abort() {
        this.onend?.();
      }
    }

    Object.defineProperty(window, "SpeechRecognition", {
      configurable: true,
      writable: true,
      value: FakeSpeechRecognition,
    });
    Object.defineProperty(window, "webkitSpeechRecognition", {
      configurable: true,
      writable: true,
      value: FakeSpeechRecognition,
    });
  });
}

test.describe("Voice input", () => {
  test.beforeEach(async ({ page }) => {
    await clearWorkspace(page);
    await seedWorkspace(page, {
      dataSourceId: DEMO_SOURCE_ID,
      dataSourceName: demoSource.name,
      sessionId: null,
      chunksEmbedded: 3,
    });
  });

  test("mic fills the composer from speech recognition", async ({ page }) => {
    await installFakeSpeechRecognition(page);
    await mockApi(page, {
      sources: [demoSource],
      sessions: [],
    });
    await page.goto("/");

    await expect(page.getByLabel("Start voice input")).toBeVisible();
    await page.getByLabel("Start voice input").click();

    await expect(page.getByLabel("Analytics question")).toHaveValue(
      "What were total sales by region?",
    );
    await expect(page.getByLabel("Start voice input")).toBeVisible();
  });

  test("play answer button appears after a successful chat", async ({ page }) => {
    await mockApi(page, {
      sources: [demoSource],
      sessions: [],
    });
    await page.addInitScript(() => {
      Object.defineProperty(window, "speechSynthesis", {
        configurable: true,
        value: {
          speaking: false,
          cancel() {
            this.speaking = false;
          },
          speak() {
            this.speaking = true;
          },
        },
      });
    });

    await page.goto("/");
    await page.getByLabel("Analytics question").fill("What were total sales by region?");
    await page.getByRole("button", { name: "Ask", exact: true }).click();

    await expect(page.getByLabel("Play answer aloud")).toBeVisible();
  });
});
