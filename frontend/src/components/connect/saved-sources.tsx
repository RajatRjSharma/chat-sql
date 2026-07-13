"use client";

import { Database } from "lucide-react";
import { cn } from "@/lib/cn";
import type { DataSourceSummary } from "@/lib/types";

type SavedSourcesProps = {
  sources: DataSourceSummary[];
  loading?: boolean;
  busy?: boolean;
  activeId?: string | null;
  onSelect: (source: DataSourceSummary) => void;
};

export function SavedSources({
  sources,
  loading,
  busy,
  activeId,
  onSelect,
}: SavedSourcesProps) {
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
            Reopen a previous connection — sessions and schema stay attached.
          </p>
        </div>
        <Database className="h-4 w-4 shrink-0 text-[var(--accent)]" aria-hidden />
      </div>

      <ul className="mt-4 space-y-2">
        {sources.map((source) => {
          const active = source.id === activeId;
          const location = [
            `${source.host}:${source.port}`,
            source.database,
            source.schema_name || "default",
          ].join(" · ");

          return (
            <li key={source.id}>
              <button
                type="button"
                disabled={busy}
                onClick={() => onSelect(source)}
                className={cn(
                  "w-full rounded-xl border px-4 py-3 text-left transition-colors",
                  "disabled:opacity-45",
                  active
                    ? "border-[var(--accent)]/45 bg-[var(--accent)]/10"
                    : "border-white/8 bg-[var(--bg-shell)]/70 hover:border-white/15 hover:bg-white/[0.04]",
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
            </li>
          );
        })}
      </ul>
    </div>
  );
}
