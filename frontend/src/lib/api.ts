import type {
  ChatRequest,
  ChatResponse,
  ChatStreamEvent,
  DataSourceSummary,
  EmbedSchemaResponse,
  SessionDetailResponse,
  SessionSummary,
  SuggestedQuestionsResponse,
  WarehouseConnectRequest,
  WarehouseConnectResponse,
} from "./types";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function parseDetail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) {
      return body.detail
        .map((item: { msg?: string }) => item.msg || JSON.stringify(item))
        .join("; ");
    }
    return JSON.stringify(body);
  } catch {
    return res.statusText || "Request failed";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });

  if (!res.ok) {
    throw new ApiError(res.status, await parseDetail(res));
  }

  return res.json() as Promise<T>;
}

function parseSseChunk(
  buffer: string,
): { events: ChatStreamEvent[]; rest: string } {
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  const events: ChatStreamEvent[] = [];

  for (const block of parts) {
    if (!block.trim()) continue;
    let eventName = "message";
    const dataLines: string[] = [];

    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim());
      }
    }

    if (!dataLines.length) continue;
    try {
      const payload = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
      if (eventName === "stage") {
        events.push({
          type: "stage",
          stage: String(payload.stage ?? ""),
          label: String(payload.label ?? "Working…"),
          attempts: Number(payload.attempts ?? 0),
          sql: (payload.sql as string | null) ?? null,
        });
      } else if (eventName === "result") {
        events.push({ type: "result", ...(payload as unknown as ChatResponse) });
      } else if (eventName === "error") {
        events.push({
          type: "error",
          detail: String(payload.detail ?? "Chat stream failed"),
        });
      }
    } catch {
      // Ignore malformed SSE frames — keep reading until a valid result/error.
    }
  }

  return { events, rest };
}

function applyStreamEvent(
  event: ChatStreamEvent,
  onEvent: ((event: ChatStreamEvent) => void) | undefined,
  state: { result: ChatResponse | null; error: string | null },
) {
  onEvent?.(event);
  if (event.type === "result") {
    state.result = {
      session_id: event.session_id,
      data_source_id: event.data_source_id,
      question: event.question,
      answer: event.answer,
      sql: event.sql,
      columns: event.columns,
      rows: event.rows,
      status: event.status,
      attempts: event.attempts,
      source_metadata: event.source_metadata ?? null,
    };
  } else if (event.type === "error") {
    state.error = event.detail;
  }
}

export const api = {
  connect(body: WarehouseConnectRequest) {
    return request<WarehouseConnectResponse>("/api/data/connect", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  embedSchema(dataSourceId: string) {
    return request<EmbedSchemaResponse>("/api/data/embed-schema", {
      method: "POST",
      body: JSON.stringify({ data_source_id: dataSourceId }),
    });
  },

  listSources() {
    return request<DataSourceSummary[]>("/api/data/sources");
  },

  suggestedQuestions(dataSourceId: string, limit = 6) {
    const params = new URLSearchParams({ limit: String(limit) });
    return request<SuggestedQuestionsResponse>(
      `/api/data/sources/${dataSourceId}/suggested-questions?${params}`,
    );
  },

  chat(body: ChatRequest) {
    return request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /**
   * Stream LangGraph progress via SSE, then resolve with the final ChatResponse.
   * Calls `onEvent` for every stage/result/error frame.
   */
  async chatStream(
    body: ChatRequest,
    onEvent?: (event: ChatStreamEvent) => void,
    signal?: AbortSignal,
  ): Promise<ChatResponse> {
    const res = await fetch(`${API_URL}/api/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });

    if (!res.ok) {
      throw new ApiError(res.status, await parseDetail(res));
    }
    if (!res.body) {
      throw new ApiError(502, "Chat stream returned an empty body");
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    const state: { result: ChatResponse | null; error: string | null } = {
      result: null,
      error: null,
    };

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parsed = parseSseChunk(buffer);
      buffer = parsed.rest;
      for (const event of parsed.events) {
        applyStreamEvent(event, onEvent, state);
      }
    }

    if (buffer.trim()) {
      const parsed = parseSseChunk(`${buffer}\n\n`);
      for (const event of parsed.events) {
        applyStreamEvent(event, onEvent, state);
      }
    }

    if (state.error) {
      throw new ApiError(502, state.error);
    }
    if (!state.result) {
      throw new ApiError(502, "Chat stream ended without a result");
    }
    return state.result;
  },

  getSession(sessionId: string) {
    return request<SessionDetailResponse>(`/api/chat/sessions/${sessionId}`);
  },

  listSessions(dataSourceId: string, limit = 50) {
    const params = new URLSearchParams({
      data_source_id: dataSourceId,
      limit: String(limit),
    });
    return request<SessionSummary[]>(`/api/chat/sessions?${params}`);
  },

  health() {
    return request<{ status: string }>("/health");
  },
};

export { API_URL };
