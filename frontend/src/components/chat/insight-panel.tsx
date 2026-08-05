"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { SpeakButton } from "@/components/chat/speak-button";
import { Button } from "@/components/ui/button";
import {
  buildSessionBrief,
  chartCarouselIdentity,
  listChartableTurns,
  type ChartableTurn,
} from "@/lib/session-brief";
import { cn } from "@/lib/cn";
import type { ChatTurn, SourceMetadata } from "@/lib/types";

const ResultChart = dynamic(
  () =>
    import("@/components/chat/result-chart").then((m) => m.ResultChart),
  { ssr: false },
);

type SchemaIndexProps = {
  chunksEmbedded: number | null;
  tablesIndexed: number | null;
  schemaIndexedAt: string | null;
  refreshBusy?: boolean;
  refreshError?: string | null;
  refreshMessage?: string | null;
  onRefreshSchemaIndex?: () => void;
};

type InsightPanelProps = {
  turns: ChatTurn[];
  dataSourceName: string;
  /** Connection-scoped warehouse provenance (available immediately after connect). */
  sourceMetadata?: SourceMetadata | null;
  /** Inline panel for mobile (no full-height aside chrome). */
  embedded?: boolean;
} & SchemaIndexProps;

function formatIndexedAt(value: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5 text-[12px] leading-snug sm:flex-row sm:items-start sm:justify-between sm:gap-3">
      <span className="shrink-0 text-[var(--text-secondary)]">{label}</span>
      <span
        className="min-w-0 break-words font-mono text-[var(--text-primary)] sm:text-right"
        title={value}
      >
        {value}
      </span>
    </div>
  );
}

function SchemaIndexBlock({
  chunksEmbedded,
  tablesIndexed,
  schemaIndexedAt,
  refreshBusy = false,
  refreshError = null,
  refreshMessage = null,
  onRefreshSchemaIndex,
}: SchemaIndexProps) {
  const indexedLabel = formatIndexedAt(schemaIndexedAt);

  return (
    <div className="mt-3 space-y-2 border-t border-[var(--border-card)] pt-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
        Schema index
      </p>
      {chunksEmbedded != null ? (
        <p className="font-mono text-[11px] text-[var(--text-secondary)]">
          {chunksEmbedded} chunk{chunksEmbedded === 1 ? "" : "s"}
          {tablesIndexed != null
            ? ` · ${tablesIndexed} table${tablesIndexed === 1 ? "" : "s"}`
            : ""}
        </p>
      ) : (
        <p className="font-mono text-[11px] text-[var(--text-secondary)]">
          Not indexed yet
        </p>
      )}
      {indexedLabel ? (
        <p className="text-[11px] text-[var(--text-secondary)]">
          Last indexed {indexedLabel}
        </p>
      ) : null}
      {onRefreshSchemaIndex ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="mt-1 h-9 w-full justify-center border border-[var(--border-card)] text-[var(--text-primary)] hover:bg-black/[0.04]"
          disabled={refreshBusy}
          onClick={onRefreshSchemaIndex}
        >
          <RefreshCw
            className={cn("h-3.5 w-3.5", refreshBusy && "animate-spin")}
            aria-hidden
          />
          {refreshBusy ? "Refreshing index…" : "Refresh schema index"}
        </Button>
      ) : null}
      {refreshMessage ? (
        <p className="text-[11px] text-[var(--text-secondary)]" role="status">
          {refreshMessage}
        </p>
      ) : null}
      {refreshError ? (
        <p className="text-[11px] text-[var(--error)]" role="alert">
          {refreshError}
        </p>
      ) : null}
    </div>
  );
}

function SourceMetadataBlock({
  meta,
  fallbackName,
  schemaIndex,
}: {
  meta: SourceMetadata | null | undefined;
  fallbackName: string;
  schemaIndex: SchemaIndexProps;
}) {
  if (!meta) {
    return (
      <>
        <p className="mt-2 break-words text-[15px] font-medium text-[var(--text-primary)]">
          {fallbackName}
        </p>
        <SchemaIndexBlock {...schemaIndex} />
      </>
    );
  }

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
      <SchemaIndexBlock {...schemaIndex} />
    </div>
  );
}

function SessionBriefCard({ turns }: { turns: ChatTurn[] }) {
  const brief = useMemo(() => buildSessionBrief(turns), [turns]);
  const speakId = useMemo(
    () =>
      `session-brief-${turns.map((t) => t.id).join("-").slice(0, 48) || "empty"}`,
    [turns],
  );

  return (
    <section className="animate-fade-in rounded-xl border border-[var(--border-card)] bg-[var(--bg-card)] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
            Session brief
          </p>
          {brief.questionCount > 0 ? (
            <p className="mt-1 font-mono text-[11px] text-[var(--text-secondary)]">
              {brief.questionCount} question{brief.questionCount === 1 ? "" : "s"}
              {" · "}
              {brief.okCount} answered
              {brief.failedCount > 0 ? ` · ${brief.failedCount} failed` : ""}
            </p>
          ) : null}
        </div>
        {brief.questionCount > 0 ? (
          <SpeakButton text={brief.text} speakId={speakId} className="shrink-0" />
        ) : null}
      </div>

      {brief.questionCount === 0 ? (
        <p className="mt-3 text-sm leading-relaxed text-[var(--text-secondary)]">
          Ask questions in this chat and a short session digest will appear here —
          key findings across the whole thread, not just the latest answer.
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {brief.bullets.map((bullet) => (
            <li
              key={bullet}
              className="break-words text-sm leading-snug text-[var(--text-primary)]"
            >
              <span className="mr-1.5 text-[var(--accent)]" aria-hidden>
                •
              </span>
              {bullet}
            </li>
          ))}
          {brief.okCount > brief.bullets.length ? (
            <li className="text-[12px] text-[var(--text-secondary)]">
              …and {brief.okCount - brief.bullets.length} earlier answer
              {brief.okCount - brief.bullets.length === 1 ? "" : "s"}
            </li>
          ) : null}
        </ul>
      )}
    </section>
  );
}

function ChartCarousel({
  items,
  index,
  onIndexChange,
}: {
  items: ChartableTurn[];
  index: number;
  onIndexChange: (index: number) => void;
}) {
  if (items.length === 0) {
    return (
      <section className="rounded-xl border border-dashed border-[var(--border-card)] bg-[var(--bg-card)] p-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
          Session charts
        </p>
        <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">
          Charts from this session will appear here. Use previous / next to browse
          every visualization without scrolling the chat.
        </p>
      </section>
    );
  }

  const current = items[index];

  return (
    <section className="animate-fade-in space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="min-w-0 shrink truncate text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
          Session charts
        </p>
        <div className="flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            aria-label="Previous chart"
            disabled={index <= 0}
            onClick={() => onIndexChange(Math.max(0, index - 1))}
            className={cn(
              "inline-flex h-8 w-8 items-center justify-center rounded-md border border-[var(--border-card)] bg-[var(--bg-card)]",
              "text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-user)]",
              "disabled:pointer-events-none disabled:opacity-35",
              "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
            )}
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="min-w-[3.25rem] text-center font-mono text-[11px] tabular-nums text-[var(--text-secondary)]">
            {index + 1} / {items.length}
          </span>
          <button
            type="button"
            aria-label="Next chart"
            disabled={index >= items.length - 1}
            onClick={() => onIndexChange(Math.min(items.length - 1, index + 1))}
            className={cn(
              "inline-flex h-8 w-8 items-center justify-center rounded-md border border-[var(--border-card)] bg-[var(--bg-card)]",
              "text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-user)]",
              "disabled:pointer-events-none disabled:opacity-35",
              "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
            )}
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      {current ? (
        <div className="space-y-2.5">
          <p
            className="line-clamp-2 break-words text-[12px] leading-snug text-[var(--text-secondary)]"
            title={current.turn.question}
          >
            <span className="font-medium text-[var(--text-primary)]">
              Q{current.index + 1}.
            </span>{" "}
            {current.turn.question}
          </p>
          <div className="w-full min-w-0 overflow-hidden">
            <ResultChart
              key={current.turn.id}
              columns={current.turn.columns}
              rows={current.turn.rows}
              compact
            />
          </div>
        </div>
      ) : null}
    </section>
  );
}

function InsightBody({
  turns,
  dataSourceName,
  sourceMetadata = null,
  ...schemaIndex
}: Omit<InsightPanelProps, "embedded">) {
  const items = useMemo(() => listChartableTurns(turns), [turns]);
  const identity = chartCarouselIdentity(items);
  const [chartIndex, setChartIndex] = useState(0);

  useEffect(() => {
    // Jump to the newest chart when the set of chartable turns changes.
    setChartIndex(items.length ? items.length - 1 : 0);
  }, [identity, items.length]);

  const safeIndex = items.length ? Math.min(chartIndex, items.length - 1) : 0;

  // Prefer connection-scoped metadata; fall back to latest turn (legacy / chat overlay).
  const warehouseMeta = useMemo(() => {
    if (sourceMetadata) return sourceMetadata;
    for (let i = turns.length - 1; i >= 0; i -= 1) {
      if (turns[i]?.source_metadata) return turns[i].source_metadata;
    }
    return null;
  }, [sourceMetadata, turns]);

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-[var(--border-card)] bg-[var(--bg-card)] p-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
          Connected warehouse
        </p>
        <SourceMetadataBlock
          meta={warehouseMeta}
          fallbackName={dataSourceName}
          schemaIndex={schemaIndex}
        />
      </section>

      <SessionBriefCard turns={turns} />

      <ChartCarousel
        items={items}
        index={safeIndex}
        onIndexChange={setChartIndex}
      />
    </div>
  );
}

export function InsightPanel({
  turns,
  dataSourceName,
  sourceMetadata = null,
  chunksEmbedded,
  tablesIndexed,
  schemaIndexedAt,
  refreshBusy,
  refreshError,
  refreshMessage,
  onRefreshSchemaIndex,
  embedded = false,
}: InsightPanelProps) {
  const bodyProps = {
    turns,
    dataSourceName,
    sourceMetadata,
    chunksEmbedded,
    tablesIndexed,
    schemaIndexedAt,
    refreshBusy,
    refreshError,
    refreshMessage,
    onRefreshSchemaIndex,
  };

  if (embedded) {
    return (
      <div className="min-w-0 bg-[var(--bg-surface)] text-[var(--text-primary)]">
        <InsightBody {...bodyProps} />
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
        <p className="mt-1 text-[12px] leading-snug text-[var(--text-secondary)]">
          Session digest and charts for this chat
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-5">
        <InsightBody {...bodyProps} />
      </div>
    </aside>
  );
}

/** Collapsible evidence block for viewports without the right rail. */
export function MobileInsightDrawer({
  turns,
  dataSourceName,
  sourceMetadata = null,
  chunksEmbedded,
  tablesIndexed,
  schemaIndexedAt,
  refreshBusy,
  refreshError,
  refreshMessage,
  onRefreshSchemaIndex,
}: Omit<InsightPanelProps, "embedded">) {
  const hasContent = turns.some((t) => t.status === "ok");

  return (
    <details
      className={cn(
        "group",
        "rounded-xl border border-[var(--border-card)] bg-[var(--bg-card)]",
      )}
    >
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-medium text-[var(--text-primary)] marker:content-none [&::-webkit-details-marker]:hidden">
        <span>Session evidence</span>
        <span className="text-[11px] font-normal uppercase tracking-[0.12em] text-[var(--text-secondary)] group-open:hidden">
          {hasContent ? "Show" : "Empty"}
        </span>
        <span className="hidden text-[11px] font-normal uppercase tracking-[0.12em] text-[var(--text-secondary)] group-open:inline">
          Hide
        </span>
      </summary>
      <div className="border-t border-[var(--border-card)] px-3 py-3 sm:px-4">
        <InsightPanel
          turns={turns}
          dataSourceName={dataSourceName}
          sourceMetadata={sourceMetadata}
          chunksEmbedded={chunksEmbedded}
          tablesIndexed={tablesIndexed}
          schemaIndexedAt={schemaIndexedAt}
          refreshBusy={refreshBusy}
          refreshError={refreshError}
          refreshMessage={refreshMessage}
          onRefreshSchemaIndex={onRefreshSchemaIndex}
          embedded
        />
      </div>
    </details>
  );
}
