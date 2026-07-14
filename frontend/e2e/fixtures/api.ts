/** Shared mock payloads for Meridian UI E2E (API is stubbed). */

export const DEMO_SOURCE_ID = "11111111-1111-4111-8111-111111111111";
export const DEMO_SOURCE_B_ID = "22222222-2222-4222-8222-222222222222";
export const SESSION_A_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
export const SESSION_B_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

export const demoSource = {
  id: DEMO_SOURCE_ID,
  name: "Demo Sales Warehouse",
  host: "localhost",
  port: 5433,
  database: "bi_warehouse",
  schema_name: "sales",
  db_type: "postgres",
  is_readonly: true,
  is_active: true,
  chunks_embedded: 3,
  session_count: 2,
};

export const demoSourceNeedsEmbed = {
  ...demoSource,
  id: DEMO_SOURCE_B_ID,
  name: "Unindexed Warehouse",
  chunks_embedded: 0,
  session_count: 0,
};

export const connectResponse = {
  data_source_id: DEMO_SOURCE_ID,
  name: "Demo Sales Warehouse",
  host: "localhost",
  port: 5433,
  database: "bi_warehouse",
  schema_name: "sales",
  status: "connected",
};

export const embedResponse = {
  data_source_id: DEMO_SOURCE_ID,
  chunks_embedded: 3,
  status: "ok",
};

export const chatOkResponse = {
  session_id: SESSION_A_ID,
  data_source_id: DEMO_SOURCE_ID,
  question: "What were total sales by region?",
  answer: "East leads with the highest sales total.",
  sql: "SELECT region, SUM(amount) AS total FROM sales.orders o JOIN sales.customers c ON c.customer_id = o.customer_id GROUP BY region",
  columns: ["region", "total"],
  rows: [
    { region: "East", total: 42000 },
    { region: "West", total: 31000 },
    { region: "North", total: 18000 },
  ],
  status: "ok" as const,
  attempts: 1,
  source_metadata: {
    source_name: "Demo Sales Warehouse",
    data_source_id: DEMO_SOURCE_ID,
    db_type: "postgres",
    engine: "PostgreSQL",
    vendor: "PostgreSQL Global Development Group",
    sql_dialect: "postgres",
    supports_schemas: true,
    identifier_quoting: "double_quote",
    dialect_notes: "Use schema.table qualification when schema is set.",
    host: "localhost",
    port: 5433,
    database: "bi_warehouse",
    schema_name: "sales",
    is_readonly: true,
    access_mode: "read_only_select",
    tables_in_context: ["orders", "customers"],
    chunks_retrieved: 3,
    context_mode: "rag",
    embedding_model: "test-embed",
    embedding_dimensions: 2048,
    llm_model: "test-llm",
    llm_model_fallback: "test-llm-fallback",
    rag_top_k: 5,
  },
};

export const suggestedQuestionsResponse = {
  data_source_id: DEMO_SOURCE_ID,
  suggestions: [
    {
      question: "What is total amount by region in orders?",
      source: "schema" as const,
      table: "orders",
    },
    {
      question: "Give me a quick summary of the products table.",
      source: "schema" as const,
      table: "products",
    },
    {
      question: "What were total sales by region?",
      source: "history" as const,
      table: null,
    },
  ],
  schema_tables: ["orders", "products", "customers"],
};

export const sessionSummaries = [
  {
    session_id: SESSION_A_ID,
    data_source_id: DEMO_SOURCE_ID,
    title: "What were total sales by region?",
    created_at: "2026-07-14T00:00:00.000Z",
    updated_at: "2026-07-14T01:00:00.000Z",
    message_count: 2,
  },
  {
    session_id: SESSION_B_ID,
    data_source_id: DEMO_SOURCE_ID,
    title: "Which products sold the most units?",
    created_at: "2026-07-13T00:00:00.000Z",
    updated_at: "2026-07-13T12:00:00.000Z",
    message_count: 4,
  },
];

export const sessionDetailA = {
  session_id: SESSION_A_ID,
  data_source_id: DEMO_SOURCE_ID,
  title: "What were total sales by region?",
  created_at: "2026-07-14T00:00:00.000Z",
  updated_at: "2026-07-14T01:00:00.000Z",
  messages: [
    { role: "user", content: "What were total sales by region?" },
    { role: "assistant", content: "East leads with the highest sales total." },
  ],
  turns: [
    {
      question: "What were total sales by region?",
      answer: "East leads with the highest sales total.",
      sql: chatOkResponse.sql,
      columns: chatOkResponse.columns,
      rows: chatOkResponse.rows,
      status: "ok" as const,
      attempts: 1,
    },
  ],
};

export const sessionDetailB = {
  session_id: SESSION_B_ID,
  data_source_id: DEMO_SOURCE_ID,
  title: "Which products sold the most units?",
  created_at: "2026-07-13T00:00:00.000Z",
  updated_at: "2026-07-13T12:00:00.000Z",
  messages: [
    { role: "user", content: "Which products sold the most units?" },
    { role: "assistant", content: "Wireless Mouse topped unit sales." },
  ],
  turns: [
    {
      question: "Which products sold the most units?",
      answer: "Wireless Mouse topped unit sales.",
      sql: "SELECT name, COUNT(*) AS units FROM sales.products GROUP BY name",
      columns: ["name", "units"],
      rows: [
        { name: "Wireless Mouse", units: 120 },
        { name: "4K Monitor", units: 40 },
      ],
      status: "ok" as const,
      attempts: 1,
    },
  ],
};
