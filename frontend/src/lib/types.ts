/** Mirrors backend Pydantic schemas used by the Meridian UI. */

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
  source_metadata?: SourceMetadata | null;
};

export type SourceMetadata = {
  source_name: string;
  data_source_id: string;
  db_type: string;
  engine: string;
  vendor: string;
  sql_dialect: string;
  supports_schemas: boolean;
  identifier_quoting: string;
  dialect_notes: string;
  host: string;
  port: number;
  database: string;
  schema_name: string | null;
  is_readonly: boolean;
  access_mode: string;
  tables_in_context: string[];
  chunks_retrieved: number;
  context_mode: string;
  embedding_model: string;
  embedding_dimensions: number;
  llm_model: string;
  llm_model_fallback: string;
  rag_top_k: number;
};

export type ChatStreamStage = {
  type: "stage";
  stage: string;
  label: string;
  attempts: number;
  sql: string | null;
};

export type ChatStreamError = {
  type: "error";
  detail: string;
};

export type ChatStreamResult = ChatResponse & { type: "result" };

export type ChatStreamEvent = ChatStreamStage | ChatStreamResult | ChatStreamError;

export type SuggestedQuestion = {
  question: string;
  source: "schema" | "history" | "fallback";
  table: string | null;
};

export type SuggestedQuestionsResponse = {
  data_source_id: string;
  suggestions: SuggestedQuestion[];
  schema_tables: string[];
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
  source_metadata?: SourceMetadata | null;
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
  source_metadata?: SourceMetadata | null;
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
  source_metadata?: SourceMetadata | null;
};
