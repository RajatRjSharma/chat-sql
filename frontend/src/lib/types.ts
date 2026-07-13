/** Mirrors backend Pydantic schemas used by the Day 3 UI. */

export type WarehouseConnectRequest = {
  name: string;
  db_type?: "postgres";
  host: string;
  port: number;
  database: string;
  schema_name?: string | null;
  username: string;
  password: string;
  is_readonly?: boolean;
};

export type WarehouseConnectResponse = {
  data_source_id: string;
  name: string;
  host: string;
  port: number;
  database: string;
  schema_name: string | null;
  status: string;
};

export type EmbedSchemaResponse = {
  data_source_id: string;
  chunks_embedded: number;
  status: string;
};

export type DataSourceSummary = {
  id: string;
  name: string;
  host: string;
  port: number;
  database: string;
  schema_name: string | null;
  db_type: string;
  is_readonly: boolean;
  is_active: boolean;
  chunks_embedded: number;
  session_count: number;
};

export type ChatRequest = {
  data_source_id: string;
  question: string;
  session_id?: string | null;
};

export type ChatResponse = {
  session_id: string;
  data_source_id: string;
  question: string;
  answer: string;
  sql: string | null;
  columns: string[];
  rows: Record<string, unknown>[];
  status: "ok" | "failed" | "running";
  attempts: number;
};

export type SessionMessage = {
  role: string;
  content: string;
};

export type SessionTurn = {
  question: string;
  answer: string;
  sql: string | null;
  columns: string[];
  rows: Record<string, unknown>[];
  status: ChatResponse["status"];
  attempts: number;
};

export type SessionSummary = {
  session_id: string;
  data_source_id: string | null;
  title: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
};

export type SessionDetailResponse = {
  session_id: string;
  data_source_id: string | null;
  title: string | null;
  created_at: string | null;
  updated_at: string | null;
  messages: SessionMessage[];
  turns: SessionTurn[];
};

export type ChatTurn = {
  id: string;
  question: string;
  answer: string;
  sql: string | null;
  columns: string[];
  rows: Record<string, unknown>[];
  status: ChatResponse["status"];
  attempts: number;
};
