import { describe, expect, it } from "vitest";
import { connectionMetadataFromSource } from "./source-metadata";
import type { DataSourceSummary, SourceMetadata } from "./types";

const baseSource: DataSourceSummary = {
  id: "11111111-1111-4111-8111-111111111111",
  name: "Demo Sales Warehouse",
  host: "localhost",
  port: 5433,
  database: "bi_warehouse",
  schema_name: "sales",
  db_type: "postgres",
  is_readonly: true,
  is_active: true,
  chunks_embedded: 3,
  session_count: 1,
};

describe("connectionMetadataFromSource", () => {
  it("prefers API source_metadata", () => {
    const meta = {
      ...baseSource,
      source_metadata: {
        source_name: "From API",
        data_source_id: baseSource.id,
        db_type: "postgres",
        engine: "PostgreSQL",
        vendor: "PostgreSQL Global Development Group",
        sql_dialect: "postgres",
        supports_schemas: true,
        identifier_quoting: "double_quote",
        dialect_notes: "notes",
        host: "db.example.com",
        port: 5432,
        database: "prod",
        schema_name: "sales",
        is_readonly: true,
        access_mode: "read_only_select",
        tables_in_context: [],
        chunks_retrieved: 0,
        context_mode: "connection",
        embedding_model: "e",
        embedding_dimensions: 8,
        llm_model: "l",
        llm_model_fallback: "f",
        rag_top_k: 5,
      } satisfies SourceMetadata,
    };

    expect(connectionMetadataFromSource(meta).source_name).toBe("From API");
    expect(connectionMetadataFromSource(meta).host).toBe("db.example.com");
  });

  it("synthesizes connection metadata when API field is missing", () => {
    const meta = connectionMetadataFromSource(baseSource);
    expect(meta.context_mode).toBe("connection");
    expect(meta.engine).toBe("PostgreSQL");
    expect(meta.database).toBe("bi_warehouse");
    expect(meta.schema_name).toBe("sales");
    expect(meta.is_readonly).toBe(true);
  });
});
