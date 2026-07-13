"use client";

import dynamic from "next/dynamic";
import { deriveChart } from "@/lib/chart";
import type { ChatTurn } from "@/lib/types";

const ResultChart = dynamic(
  () =>
    import("@/components/chat/result-chart").then((m) => m.ResultChart),
  { ssr: false },
);

type InsightPanelProps = {
  latest: ChatTurn | null;
  dataSourceName: string;
  chunksEmbedded: number | null;
};

export function InsightPanel({
  latest,
  dataSourceName,
  chunksEmbedded,
}: InsightPanelProps) {
  const chartable =
    latest && latest.status === "ok"
      ? deriveChart(latest.columns, latest.rows).kind !== "none"
      : false;

  return (
    <aside className="flex h-full flex-col border-l border-[var(--border-card)] bg-[var(--bg-surface)]">
      <div className="border-b border-[var(--border-card)] px-5 py-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
          Insight
        </p>
        <p className="mt-1 font-[family-name:var(--font-display)] text-xl tracking-tight text-[var(--text-primary)]">
          Evidence panel
        </p>
      </div>

      <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
        <section className="rounded-xl border border-[var(--border-card)] bg-[var(--bg-card)] p-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
            Data source
          </p>
          <p className="mt-2 text-[15px] font-medium text-[var(--text-primary)]">
            {dataSourceName}
          </p>
          {chunksEmbedded != null ? (
            <p className="mt-1 font-mono text-xs text-[var(--text-secondary)]">
              {chunksEmbedded} schema chunk{chunksEmbedded === 1 ? "" : "s"} indexed
            </p>
          ) : null}
        </section>

        {latest?.status === "ok" && latest.answer ? (
          <section className="animate-fade-in rounded-xl border border-[var(--border-card)] bg-[var(--bg-card)] p-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
              Latest summary
            </p>
            <p className="mt-2 text-sm leading-relaxed text-[var(--text-primary)]">
              {latest.answer}
            </p>
          </section>
        ) : (
          <section className="rounded-xl border border-dashed border-[var(--border-card)] p-4">
            <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
              After you ask a question, the summary and chart for the latest answer
              appear here.
            </p>
          </section>
        )}

        {latest && chartable ? (
          <ResultChart columns={latest.columns} rows={latest.rows} />
        ) : null}
      </div>
    </aside>
  );
}
