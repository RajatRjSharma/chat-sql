import type { WarehouseConnectRequest } from "./types";

/** Local Makefile demo warehouse — matches `make warehouse-seed` defaults. */
export const DEMO_WAREHOUSE: WarehouseConnectRequest = {
  name: "Demo Sales Warehouse",
  db_type: "postgres",
  host: "localhost",
  port: 5433,
  database: "bi_warehouse",
  schema_name: "sales",
  username: "bi_readonly",
  password: "readonly_pass",
  is_readonly: true,
};

export const SUGGESTED_QUESTIONS = [
  "What were total sales by region?",
  "Which products sold the most units?",
  "Summarize the sales tables in this warehouse.",
  "What is average order value by region?",
] as const;

const STORAGE_KEY = "vda.workspace.v1";

export type PersistedWorkspace = {
  dataSourceId: string;
  dataSourceName: string;
  sessionId: string | null;
  chunksEmbedded: number | null;
};

export function loadWorkspace(): PersistedWorkspace | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as PersistedWorkspace;
  } catch {
    return null;
  }
}

export function saveWorkspace(state: PersistedWorkspace) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

export function clearWorkspace() {
  sessionStorage.removeItem(STORAGE_KEY);
}
