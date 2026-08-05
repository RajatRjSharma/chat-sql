import type { DataSourceSummary, SourceMetadata } from "./types";

/** Postgres profile defaults — mirrors backend `resolve_engine_profile`. */
const ENGINE_DEFAULTS: Record<
  string,
  Pick<
    SourceMetadata,
    | "engine"
    | "vendor"
    | "sql_dialect"
    | "supports_schemas"
    | "identifier_quoting"
    | "dialect_notes"
  >
> = {
  postgres: {
    engine: "PostgreSQL",
    vendor: "PostgreSQL Global Development Group",
    sql_dialect: "postgres",
    supports_schemas: true,
    identifier_quoting: "double_quote",
    dialect_notes:
      "Use schema.table qualification when schema is set. FILTER / CTEs OK.",
  },
};

/**
 * Prefer API `source_metadata`; otherwise synthesize connection provenance
 * from a data-source summary (reload / older clients).
 */
export function connectionMetadataFromSource(
  source: Pick<
    DataSourceSummary,
    | "id"
    | "name"
    | "host"
    | "port"
    | "database"
    | "schema_name"
    | "db_type"
    | "is_readonly"
  > & { source_metadata?: SourceMetadata | null },
): SourceMetadata {
  if (source.source_metadata) {
    return source.source_metadata;
  }

  const key = (source.db_type || "postgres").toLowerCase();
  const profile = ENGINE_DEFAULTS[key] ?? {
    engine: key,
    vendor: "unknown",
    sql_dialect: key,
    supports_schemas: true,
    identifier_quoting: "double_quote",
    dialect_notes: "Generate standard SQL SELECT for this engine.",
  };

  return {
    source_name: source.name,
    data_source_id: source.id,
    db_type: key,
    ...profile,
    host: source.host,
    port: source.port,
    database: source.database,
    schema_name: source.schema_name,
    is_readonly: source.is_readonly,
    access_mode: "read_only_select",
    tables_in_context: [],
    chunks_retrieved: 0,
    context_mode: "connection",
    embedding_model: "",
    embedding_dimensions: 0,
    llm_model: "",
    llm_model_fallback: "",
    rag_top_k: 0,
  };
}
