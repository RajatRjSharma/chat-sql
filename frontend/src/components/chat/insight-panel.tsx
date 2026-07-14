"use client";

import dynamic from "next/dynamic";
import { Volume2, VolumeX } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { deriveChart } from "@/lib/chart";
import {
  isSpeechSynthesisSupported,
  speakText,
  stopSpeaking,
} from "@/lib/speech";
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
};

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 text-[12px] leading-snug">
      <span className="shrink-0 text-[var(--text-secondary)]">{label}</span>
      <span className="text-right font-mono text-[var(--text-primary)]">{value}</span>
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
        <p className="mt-2 text-[15px] font-medium text-[var(--text-primary)]">
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
      <p className="text-[15px] font-medium text-[var(--text-primary)]">
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

export function InsightPanel({
  latest,
  dataSourceName,
  chunksEmbedded,
}: InsightPanelProps) {
  const [ttsSupported, setTtsSupported] = useState(false);
  const [speaking, setSpeaking] = useState(false);

  const chartable =
    latest && latest.status === "ok"
      ? deriveChart(latest.columns, latest.rows).kind !== "none"
      : false;

  useEffect(() => {
    setTtsSupported(isSpeechSynthesisSupported());
  }, []);

  useEffect(() => {
    stopSpeaking();
    setSpeaking(false);
  }, [latest?.id, latest?.answer]);

  useEffect(() => {
    return () => stopSpeaking();
  }, []);

  function handleToggleSpeak() {
    if (!latest?.answer) return;
    if (speaking) {
      stopSpeaking();
      setSpeaking(false);
      return;
    }
    speakText(latest.answer);
    setSpeaking(true);
    const check = window.setInterval(() => {
      if (!window.speechSynthesis.speaking) {
        setSpeaking(false);
        window.clearInterval(check);
      }
    }, 250);
  }

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
              {ttsSupported ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-8 px-2"
                  onClick={handleToggleSpeak}
                  aria-label={speaking ? "Stop reading answer" : "Play answer aloud"}
                >
                  {speaking ? (
                    <VolumeX className="h-4 w-4" />
                  ) : (
                    <Volume2 className="h-4 w-4" />
                  )}
                </Button>
              ) : null}
            </div>
            <p className="mt-2 text-sm leading-relaxed text-[var(--text-primary)]">
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
          <ResultChart columns={latest.columns} rows={latest.rows} />
        ) : null}
      </div>
    </aside>
  );
}
