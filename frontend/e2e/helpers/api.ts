import type { Page, Route } from "@playwright/test";
import {
  chatOkResponse,
  connectResponse,
  demoSource,
  demoUser,
  embedResponse,
  sessionDetailA,
  sessionDetailB,
  sessionSummaries,
  suggestedQuestionsResponse,
  uploadResponse,
  SESSION_A_ID,
  SESSION_B_ID,
} from "../fixtures/api";

type Json = unknown;

async function fulfill(route: Route, body: Json, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function sseBody(frames: { event: string; data: Json }[]) {
  return frames
    .map(
      (frame) =>
        `event: ${frame.event}\ndata: ${JSON.stringify(frame.data)}\n\n`,
    )
    .join("");
}

export type MockApiOptions = {
  sources?: Json[];
  connect?: Json;
  embed?: Json;
  upload?: Json;
  chat?: Json | ((payload: unknown) => Json);
  suggestions?: Json;
  sessions?: Json[];
  sessionDetails?: Record<string, Json>;
  connectStatus?: number;
  uploadStatus?: number;
  chatStatus?: number;
};

/**
 * Stub FastAPI routes used by the Meridian UI.
 * Paths match NEXT_PUBLIC_API_URL (http://127.0.0.1:8000).
 */
export async function mockApi(page: Page, options: MockApiOptions = {}) {
  const sources = options.sources ?? [];
  const connect = options.connect ?? connectResponse;
  const embed = options.embed ?? embedResponse;
  const upload = options.upload ?? uploadResponse;
  const sessions = options.sessions ?? sessionSummaries;
  const suggestions = options.suggestions ?? suggestedQuestionsResponse;
  const sessionDetails = options.sessionDetails ?? {
    [SESSION_A_ID]: sessionDetailA,
    [SESSION_B_ID]: sessionDetailB,
  };
  const chat =
    options.chat ??
    ((payload: unknown) => {
      const body = payload as { question?: string; session_id?: string | null };
      return {
        ...chatOkResponse,
        question: body.question || chatOkResponse.question,
        session_id: body.session_id || chatOkResponse.session_id,
      };
    });

  await page.addInitScript((user) => {
    try {
      localStorage.setItem(
        "meridian.auth.v2",
        JSON.stringify({
          accessToken: "e2e-test-token",
          refreshToken: "e2e-refresh-token",
          expiresAt: Date.now() + 60 * 60 * 1000,
          user,
        }),
      );
    } catch {
      /* ignore */
    }
  }, demoUser);

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const method = request.method();
    const url = new URL(request.url());
    const path = url.pathname;

    if (method === "GET" && path === "/api/auth/me") {
      return fulfill(route, demoUser);
    }
    if (method === "POST" && path === "/api/auth/logout") {
      return fulfill(route, { status: "ok", message: "Logged out" });
    }
    if (method === "POST" && path === "/api/auth/login") {
      return fulfill(route, {
        access_token: "e2e-test-token",
        refresh_token: "e2e-refresh-token",
        token_type: "bearer",
        expires_in: 1800,
        user: demoUser,
      });
    }
    if (method === "POST" && path === "/api/auth/register") {
      return fulfill(
        route,
        {
          status: "otp_sent",
          email: "analyst@example.com",
          message: "Verification code sent to your email.",
        },
        201,
      );
    }
    if (method === "POST" && path === "/api/auth/verify-otp") {
      return fulfill(route, {
        access_token: "e2e-test-token",
        refresh_token: "e2e-refresh-token",
        token_type: "bearer",
        expires_in: 1800,
        user: demoUser,
      });
    }
    if (method === "POST" && path === "/api/auth/refresh") {
      return fulfill(route, {
        access_token: "e2e-test-token",
        refresh_token: "e2e-refresh-token",
        token_type: "bearer",
        expires_in: 1800,
        user: demoUser,
      });
    }
    if (method === "POST" && path === "/api/auth/resend-otp") {
      return fulfill(route, {
        status: "otp_sent",
        email: "analyst@example.com",
        message: "A new verification code was sent.",
      });
    }

    if (method === "GET" && path === "/api/data/sources") {
      return fulfill(route, sources);
    }

    const deleteMatch = path.match(/^\/api\/data\/sources\/([^/]+)$/);
    if (method === "DELETE" && deleteMatch) {
      return route.fulfill({ status: 204, body: "" });
    }

    const suggestedMatch = path.match(
      /^\/api\/data\/sources\/([^/]+)\/suggested-questions$/,
    );
    if (method === "GET" && suggestedMatch) {
      return fulfill(route, suggestions);
    }

    if (method === "POST" && path === "/api/data/connect") {
      if (options.connectStatus && options.connectStatus >= 400) {
        return fulfill(
          route,
          { detail: "Could not connect to warehouse: mocked failure" },
          options.connectStatus,
        );
      }
      return fulfill(route, connect);
    }

    if (method === "POST" && path === "/api/data/upload") {
      if (options.uploadStatus && options.uploadStatus >= 400) {
        return fulfill(
          route,
          { detail: "Unsupported file type. Upload a .csv or .xlsx file." },
          options.uploadStatus,
        );
      }
      return fulfill(route, upload);
    }

    if (method === "POST" && path === "/api/data/embed-schema") {
      return fulfill(route, embed);
    }

    const resolveChatBody = () => {
      const payload = request.postDataJSON();
      return typeof chat === "function" ? chat(payload) : chat;
    };

    if (method === "POST" && path === "/api/chat/stream") {
      if (options.chatStatus && options.chatStatus >= 400) {
        return fulfill(
          route,
          { detail: "AI provider error: mocked upstream failure" },
          options.chatStatus,
        );
      }
      const body = resolveChatBody() as Record<string, unknown>;
      const stream = sseBody([
        {
          event: "stage",
          data: {
            stage: "generate_sql",
            label: "Generating SQL",
            attempts: 0,
            sql: null,
          },
        },
        {
          event: "stage",
          data: {
            stage: "summarize",
            label: "Summarizing results",
            attempts: 1,
            sql: body.sql ?? null,
          },
        },
        { event: "result", data: body },
      ]);
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: stream,
      });
    }

    if (method === "POST" && path === "/api/chat") {
      if (options.chatStatus && options.chatStatus >= 400) {
        return fulfill(
          route,
          { detail: "AI provider error: mocked upstream failure" },
          options.chatStatus,
        );
      }
      return fulfill(route, resolveChatBody());
    }

    if (method === "GET" && path === "/api/chat/sessions") {
      return fulfill(route, sessions);
    }

    const sessionMatch = path.match(/^\/api\/chat\/sessions\/([^/]+)$/);
    if (method === "GET" && sessionMatch) {
      const id = sessionMatch[1];
      const detail = sessionDetails[id];
      if (!detail) {
        return fulfill(route, { detail: "Session not found" }, 404);
      }
      return fulfill(route, detail);
    }

    return fulfill(route, { detail: `Unmocked ${method} ${path}` }, 404);
  });
}

export async function clearWorkspace(page: Page) {
  await page.addInitScript(() => {
    try {
      sessionStorage.removeItem("vda.workspace.v1");
      localStorage.removeItem("meridian.auth.v1");
      localStorage.removeItem("meridian.auth.v2");
    } catch {
      /* ignore */
    }
  });
}

export async function seedWorkspace(
  page: Page,
  workspace: {
    dataSourceId: string;
    dataSourceName: string;
    sessionId: string | null;
    chunksEmbedded: number | null;
  },
) {
  await page.addInitScript((value) => {
    sessionStorage.setItem("vda.workspace.v1", JSON.stringify(value));
  }, workspace);
}

export { demoSource, chatOkResponse, SESSION_A_ID, SESSION_B_ID };
