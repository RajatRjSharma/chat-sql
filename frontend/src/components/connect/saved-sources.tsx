"use client";

import { useState } from "react";
import { Database, Trash2 } from "lucide-react";
import { cn } from "@/lib/cn";
import type { DataSourceSummary } from "@/lib/types";

type SavedSourcesProps = {
  sources: DataSourceSummary[];
  loading?: boolean;
  busy?: boolean;
  activeId?: string | null;
  deletingId?: string | null;
  onSelect: (source: DataSourceSummary) => void;
  onDelete: (source: DataSourceSummary) => void;
};

export function SavedSources({
  sources,
  loading,
  busy,
  activeId,
  deletingId,
  onSelect,
  onDelete,
}: SavedSourcesProps) {
  const [confirmId, setConfirmId] = useState<string | null>(null);

  if (loading) {
    return (
      <div className="rounded-2xl border border-white/10 bg-[var(--bg-shell-elevated)]/60 px-5 py-4">
        <p className="text-xs text-[var(--text-muted-dark)]">Loading saved warehouses…</p>
      </div>
    );
  }

  if (sources.length === 0) {
    return null;
  }

  return (
    <div className="rounded-2xl border border-white/10 bg-[var(--bg-shell-elevated)]/80 p-5 shadow-[0_24px_60px_-40px_rgba(0,0,0,0.65)] backdrop-blur-sm animate-rise">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted-dark)]">
            Saved warehouses
          </p>
          <p className="mt-1 text-sm text-[var(--text-muted-dark)]">
            Reopen a previous connection — or remove ones you no longer need.
          </p>
        </div>
        <Database className="h-4 w-4 shrink-0 text-[var(--accent)]" aria-hidden />
      </div>

      <ul className="mt-4 space-y-2">
        {sources.map((source) => {
          const active = source.id === activeId;
          const deleting = source.id === deletingId;
          const confirming = confirmId === source.id;
          const location = [
            `${source.host}:${source.port}`,
            source.database,
            source.schema_name || "default",
          ].join(" · ");

          return (
            <li key={source.id}>
              <div
                className={cn(
                  "flex items-stretch gap-2 rounded-xl border transition-colors",
                  active
                    ? "border-[var(--accent)]/45 bg-[var(--accent)]/10"
                    : "border-white/8 bg-[var(--bg-shell)]/70",
                )}
              >
                <button
                  type="button"
                  disabled={busy || deleting}
                  onClick={() => {
                    setConfirmId(null);
                    onSelect(source);
                  }}
                  className={cn(
                    "min-w-0 flex-1 rounded-xl px-4 py-3 text-left",
                    "disabled:opacity-45",
                    !active && "hover:bg-white/[0.04]",
                  )}
                >
                  <span className="block font-[family-name:var(--font-display)] text-[15px] tracking-tight text-[var(--text-on-dark)]">
                    {source.name}
                  </span>
                  <span className="mt-1 block font-mono text-[11px] text-[var(--text-muted-dark)]">
                    {location}
                  </span>
                  <span className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-[var(--text-muted-dark)]">
                    <span>
                      {source.session_count} session
                      {source.session_count === 1 ? "" : "s"}
                    </span>
                    <span>
                      {source.chunks_embedded} schema chunk
                      {source.chunks_embedded === 1 ? "" : "s"}
                    </span>
                    {source.is_readonly ? <span>read-only</span> : null}
                  </span>
                </button>

                <div className="flex shrink-0 flex-col items-end justify-center gap-1 pr-2">
                  {confirming ? (
                    <div className="flex flex-col items-end gap-1 py-1">
                      <button
                        type="button"
                        disabled={busy || deleting}
                        onClick={() => {
                          setConfirmId(null);
                          onDelete(source);
                        }}
                        className="rounded-md bg-[var(--error)]/15 px-2.5 py-1 text-[11px] font-medium text-[#fecaca] hover:bg-[var(--error)]/25 disabled:opacity-45"
                      >
                        {deleting ? "Removing…" : "Remove"}
                      </button>
                      <button
                        type="button"
                        disabled={deleting}
                        onClick={() => setConfirmId(null)}
                        className="px-2.5 py-0.5 text-[11px] text-[var(--text-muted-dark)] hover:text-[var(--text-on-dark)]"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      disabled={busy || deleting}
                      aria-label={`Remove ${source.name}`}
                      title="Remove saved warehouse"
                      onClick={(e) => {
                        e.stopPropagation();
                        setConfirmId(source.id);
                      }}
                      className={cn(
                        "rounded-lg p-2 text-[var(--text-muted-dark)] transition-colors",
                        "hover:bg-[var(--error)]/10 hover:text-[#fecaca]",
                        "disabled:opacity-45",
                      )}
                    >
                      <Trash2 className="h-4 w-4" aria-hidden />
                    </button>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
