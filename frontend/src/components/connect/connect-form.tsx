"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";
import { DEMO_WAREHOUSE } from "@/lib/demo";
import type { WarehouseConnectRequest } from "@/lib/types";

type ConnectFormProps = {
  onConnected: (payload: {
    dataSourceId: string;
    dataSourceName: string;
    chunksEmbedded: number;
  }) => void;
};

type Phase = "idle" | "connecting" | "embedding" | "done";

export function ConnectForm({ onConnected }: ConnectFormProps) {
  const [form, setForm] = useState<WarehouseConnectRequest>({ ...DEMO_WAREHOUSE });
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);

  function update<K extends keyof WarehouseConnectRequest>(
    key: K,
    value: WarehouseConnectRequest[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setPhase("connecting");

    try {
      const connected = await api.connect({
        ...form,
        schema_name: form.schema_name?.trim() || null,
        port: Number(form.port),
      });

      setPhase("embedding");
      const embedded = await api.embedSchema(connected.data_source_id);

      setPhase("done");
      onConnected({
        dataSourceId: connected.data_source_id,
        dataSourceName: connected.name,
        chunksEmbedded: embedded.chunks_embedded,
      });
    } catch (err) {
      setPhase("idle");
      setError(err instanceof ApiError ? err.detail : "Connection failed");
    }
  }

  const busy = phase === "connecting" || phase === "embedding";

  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-[var(--bg-shell-elevated)]/80 p-8 shadow-[0_40px_80px_-40px_rgba(0,0,0,0.7)] backdrop-blur-sm animate-rise">
      <div
        aria-hidden
        className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-[var(--accent)]/15 blur-3xl"
      />
      <div className="relative">
        <p className="font-[family-name:var(--font-display)] text-2xl tracking-tight text-[var(--text-on-dark)]">
          Connect warehouse
        </p>
        <p className="mt-2 max-w-md text-sm leading-relaxed text-[var(--text-muted-dark)]">
          Credentials are validated, encrypted, and schema-indexed for retrieval.
          Demo defaults are prefilled for local development.
        </p>

        <form onSubmit={handleSubmit} className="mt-8 space-y-5">
          <Field label="Display name">
            <Input
              value={form.name}
              onChange={(e) => update("name", e.target.value)}
              required
              disabled={busy}
              className="border-white/10 bg-[var(--bg-shell)] text-[var(--text-on-dark)] placeholder:text-[var(--text-muted-dark)] focus:ring-[var(--accent)]/30"
            />
          </Field>

          <div className="grid gap-5 sm:grid-cols-[1fr_120px]">
            <Field label="Host">
              <Input
                value={form.host}
                onChange={(e) => update("host", e.target.value)}
                required
                disabled={busy}
                className="border-white/10 bg-[var(--bg-shell)] text-[var(--text-on-dark)] focus:ring-[var(--accent)]/30"
              />
            </Field>
            <Field label="Port">
              <Input
                type="number"
                value={form.port}
                onChange={(e) => update("port", Number(e.target.value))}
                required
                disabled={busy}
                className="border-white/10 bg-[var(--bg-shell)] text-[var(--text-on-dark)] focus:ring-[var(--accent)]/30"
              />
            </Field>
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Database">
              <Input
                value={form.database}
                onChange={(e) => update("database", e.target.value)}
                required
                disabled={busy}
                className="border-white/10 bg-[var(--bg-shell)] text-[var(--text-on-dark)] focus:ring-[var(--accent)]/30"
              />
            </Field>
            <Field label="Schema (optional)">
              <Input
                value={form.schema_name ?? ""}
                onChange={(e) => update("schema_name", e.target.value)}
                disabled={busy}
                placeholder="public"
                className="border-white/10 bg-[var(--bg-shell)] text-[var(--text-on-dark)] focus:ring-[var(--accent)]/30"
              />
            </Field>
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Username">
              <Input
                value={form.username}
                onChange={(e) => update("username", e.target.value)}
                required
                disabled={busy}
                autoComplete="username"
                className="border-white/10 bg-[var(--bg-shell)] text-[var(--text-on-dark)] focus:ring-[var(--accent)]/30"
              />
            </Field>
            <Field label="Password">
              <Input
                type="password"
                value={form.password}
                onChange={(e) => update("password", e.target.value)}
                required
                disabled={busy}
                autoComplete="current-password"
                className="border-white/10 bg-[var(--bg-shell)] text-[var(--text-on-dark)] focus:ring-[var(--accent)]/30"
              />
            </Field>
          </div>

          {error ? (
            <p
              role="alert"
              className="rounded-md border border-[var(--error)]/30 bg-[var(--error)]/10 px-3 py-2 text-sm text-[#fecaca]"
            >
              {error}
            </p>
          ) : null}

          <div className="flex flex-col gap-3 pt-2 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-[var(--text-muted-dark)]">
              {phase === "connecting" && "Validating connection…"}
              {phase === "embedding" && "Indexing schema for RAG…"}
              {phase === "idle" && "Read-only role recommended."}
              {phase === "done" && "Ready."}
            </p>
            <Button type="submit" size="lg" disabled={busy} className="min-w-[180px]">
              {busy ? "Working…" : "Connect & index"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div>
      <Label className="text-[var(--text-muted-dark)]">{label}</Label>
      {children}
    </div>
  );
}
