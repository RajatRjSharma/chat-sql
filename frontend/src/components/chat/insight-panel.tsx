"use client";

import dynamic from "next/dynamic";
import { SpeakButton } from "@/components/chat/speak-button";
import { deriveChart } from "@/lib/chart";
import { cn } from "@/lib/cn";
import type { ChatTurn, SourceMetadata } from "@/lib/types";

const ResultChart = dynamic(
  () =>
    import("@/components/chat/result-chart").then((m) => m.ResultChart),
  { ssr: false },
);

type InsightPanelProps = {
  latest: ChatTurn | null;
  dataSourceName: string;
  chunksEmbedded: number | null;
  /** Inline panel for mobile (no full-height aside chrome). */
  embedded?: boolean;
};

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 text-[12px] leading-snug">
      <span className="shrink-0 text-[var(--text-secondary)]">{label}</span>
      <span className="min-w-0 break-words text-right font-mono text-[var(--text-primary)]">
        {value}
      </span>
    </div>
  );
}

function SourceMetadataBlock({
  meta,
  fallbackName,
  chunksEmbedded,
}: {
  meta: SourceMetadata | null | undefined;
  fallbackName: string;
  chunksEmbedded: number | null;
}) {
  if (!meta) {
    return (
      <>
        <p className="mt-2 break-words text-[15px] font-medium text-[var(--text-primary)]">
          {fallbackName}
        </p>
        {chunksEmbedded != null ? (
          <p className="mt-1 font-mono text-xs text-[var(--text-secondary)]">
            {chunksEmbedded} schema chunk{chunksEmbedded === 1 ? "" : "s"} indexed
          </p>
        ) : null}
      </>
    );
  }

  const tables =
    meta.tables_in_context.length > 0
      ? meta.tables_in_context.slice(0, 6).join(", ")
      : "—";

  return (
    <div className="mt-3 space-y-2">
      <p className="break-words text-[15px] font-medium text-[var(--text-primary)]">
        {meta.source_name || fallbackName}
      </p>
      <MetaRow label="Engine" value={`${meta.engine} · ${meta.db_type}`} />
      <MetaRow label="Vendor" value={meta.vendor} />
      <MetaRow label="Dialect" value={meta.sql_dialect} />
      <MetaRow
        label="Database"
        value={`${meta.database}${meta.schema_name ? `.${meta.schema_name}` : ""}`}
      />
      <MetaRow label="Host" value={`${meta.host}:${meta.port}`} />
      <MetaRow
        label="Access"
        value={meta.is_readonly ? "read-only SELECT" : meta.access_mode}
      />
      <MetaRow label="Context tables" value={tables} />
      <MetaRow
        label="RAG"
        value={`${meta.chunks_retrieved} chunk${meta.chunks_retrieved === 1 ? "" : "s"} · ${meta.context_mode}`}
      />
      {chunksEmbedded != null ? (
        <p className="pt-1 font-mono text-[11px] text-[var(--text-secondary)]">
          {chunksEmbedded} schema chunk{chunksEmbedded === 1 ? "" : "s"} indexed total
        </p>
      ) : null}
    </div>
  );
}

function InsightBody({
  latest,
  dataSourceName,
  chunksEmbedded,
}: Omit<InsightPanelProps, "embedded">) {
  const chartable =
    latest && latest.status === "ok"
      ? deriveChart(latest.columns, latest.rows).kind !== "none"
      : false;

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-[var(--border-card)] bg-[var(--bg-card)] p-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
          Response provenance
        </p>
        <SourceMetadataBlock
          meta={latest?.source_metadata}
          fallbackName={dataSourceName}
          chunksEmbedded={chunksEmbedded}
        />
      </section>

      {latest?.status === "ok" && latest.answer ? (
        <section className="animate-fade-in rounded-xl border border-[var(--border-card)] bg-[var(--bg-card)] p-4">
          <div className="flex items-start justify-between gap-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
              Latest summary
            </p>
            <SpeakButton
              text={latest.answer}
              speakId={`insight-${latest.id}`}
            />
          </div>
          <p className="mt-2 break-words text-sm leading-relaxed text-[var(--text-primary)]">
            {latest.answer}
          </p>
        </section>
      ) : (
        <section className="rounded-xl border border-dashed border-[var(--border-card)] p-4">
          <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
            After you ask a question, the summary and chart for the latest answer
            appear here — with engine, dialect, and model provenance for that turn.
          </p>
        </section>
      )}

      {latest && chartable ? (
        <div className="w-full min-w-0">
          <ResultChart columns={latest.columns} rows={latest.rows} />
        </div>
      ) : null}
    </div>
  );
}

export function InsightPanel({
  latest,
  dataSourceName,
  chunksEmbedded,
  embedded = false,
}: InsightPanelProps) {
  if (embedded) {
    return (
      <div className="min-w-0 bg-[var(--bg-surface)] text-[var(--text-primary)]">
        <InsightBody
          latest={latest}
          dataSourceName={dataSourceName}
          chunksEmbedded={chunksEmbedded}
        />
      </div>
    );
  }

  return (
    <aside className="flex h-full min-w-0 flex-col border-l border-[var(--border-card)] bg-[var(--bg-surface)]">
      <div className="shrink-0 border-b border-[var(--border-card)] px-5 py-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
          Insight
        </p>
        <p className="mt-1 font-[family-name:var(--font-display)] text-xl tracking-tight text-[var(--text-primary)]">
          Evidence panel
        </p>
      </div>

      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto overscroll-contain px-5 py-5">
        <InsightBody
          latest={latest}
          dataSourceName={dataSourceName}
          chunksEmbedded={chunksEmbedded}
        />
      </div>
    </aside>
  );
}

/** Collapsible evidence block for viewports without the right rail. */
export function MobileInsightDrawer({
  latest,
  dataSourceName,
  chunksEmbedded,
}: Omit<InsightPanelProps, "embedded">) {
  const hasContent = latest != null && latest.status === "ok";

  return (
    <details
      className={cn(
        "group",
        "rounded-xl border border-[var(--border-card)] bg-[var(--bg-card)]",
      )}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-medium text-[var(--text-primary)] marker:content-none [&::-webkit-details-marker]:hidden">
        <span>Evidence & provenance</span>
        <span className="text-[11px] font-normal uppercase tracking-[0.12em] text-[var(--text-secondary)] group-open:hidden">
          {hasContent ? "Show" : "Empty"}
        </span>
        <span className="hidden text-[11px] font-normal uppercase tracking-[0.12em] text-[var(--text-secondary)] group-open:inline">
          Hide
        </span>
      </summary>
      <div className="border-t border-[var(--border-card)] px-3 py-3 sm:px-4">
        <InsightPanel
          latest={latest}
          dataSourceName={dataSourceName}
          chunksEmbedded={chunksEmbedded}
          embedded
        />
      </div>
    </details>
  );
}
