import type {
  ChatRequest,
  ChatResponse,
  DataSourceSummary,
  EmbedSchemaResponse,
  SessionDetailResponse,
  SessionSummary,
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

  chat(body: ChatRequest) {
    return request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify(body),
    });
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
