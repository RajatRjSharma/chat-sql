"use client";

import dynamic from "next/dynamic";
import { ResultTable } from "@/components/chat/result-table";
import { SpeakButton } from "@/components/chat/speak-button";
import { SqlDisclosure } from "@/components/chat/sql-disclosure";
import type { ChatTurn } from "@/lib/types";
import { cn } from "@/lib/cn";

const ResultChart = dynamic(
  () =>
    import("@/components/chat/result-chart").then((m) => m.ResultChart),
  {
    ssr: false,
    loading: () => (
      <div className="h-[220px] w-full min-w-0 animate-pulse rounded-xl border border-[var(--border-card)] bg-[var(--bg-card)]" />
    ),
  },
);

type MessageListProps = {
  turns: ChatTurn[];
  pendingQuestion: string | null;
  pendingStageLabel?: string | null;
};

export function MessageList({
  turns,
  pendingQuestion,
  pendingStageLabel = null,
}: MessageListProps) {
  if (!turns.length && !pendingQuestion) {
    return (
      <div className="flex h-full min-h-[240px] flex-col items-center justify-center px-4 text-center animate-fade-in sm:min-h-[280px] sm:px-6">
        <p className="font-[family-name:var(--font-display)] text-2xl tracking-tight text-[var(--text-primary)] sm:text-3xl md:text-4xl">
          Ask anything about the warehouse
        </p>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-[var(--text-secondary)] sm:text-[15px]">
          Questions become validated SQL, executed read-only, then summarized with a
          chart when the result shape allows.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 sm:space-y-8">
      {turns.map((turn) => (
        <article key={turn.id} className="min-w-0 space-y-3 sm:space-y-4 animate-rise">
          <div className="flex justify-end">
            <div className="max-w-[min(100%,36rem)] break-words rounded-2xl rounded-br-md bg-[var(--bg-user)] px-3 py-2.5 text-[14px] leading-relaxed text-[var(--text-primary)] sm:max-w-[85%] sm:px-4 sm:py-3 sm:text-[15px]">
              {turn.question}
            </div>
          </div>

          <div className="w-full min-w-0 max-w-full space-y-3 sm:max-w-[95%]">
            <div
              className={cn(
                "rounded-2xl rounded-bl-md border px-3 py-2.5 text-[14px] leading-relaxed sm:px-4 sm:py-3 sm:text-[15px]",
                turn.status === "failed"
                  ? "border-[var(--error)]/25 bg-[var(--error)]/5 text-[var(--error)]"
                  : "border-[var(--border-card)] bg-[var(--bg-card)] text-[var(--text-primary)] shadow-[0_1px_0_rgba(15,23,42,0.04)]",
              )}
            >
              {turn.status === "ok" && turn.answer ? (
                <div className="flex items-start gap-2">
                  <p className="min-w-0 flex-1 break-words">{turn.answer}</p>
                  <SpeakButton
                    text={turn.answer}
                    speakId={`turn-${turn.id}`}
                    className="shrink-0 -mr-1 -mt-0.5"
                  />
                </div>
              ) : (
                <span className="break-words">{turn.answer}</span>
              )}
            </div>

            {turn.status === "ok" && turn.rows.length > 0 ? (
              <>
                <div className="w-full min-w-0">
                  <ResultChart
                    columns={turn.columns}
                    rows={turn.rows}
                    compact
                    question={turn.question}
                  />
                </div>
                <ResultTable columns={turn.columns} rows={turn.rows} />
              </>
            ) : null}

            <SqlDisclosure sql={turn.sql} attempts={turn.attempts} />
          </div>
        </article>
      ))}

      {pendingQuestion ? (
        <article className="min-w-0 space-y-3 sm:space-y-4 animate-rise">
          <div className="flex justify-end">
            <div className="max-w-[min(100%,36rem)] break-words rounded-2xl rounded-br-md bg-[var(--bg-user)] px-3 py-2.5 text-[14px] leading-relaxed text-[var(--text-primary)] sm:max-w-[85%] sm:px-4 sm:py-3 sm:text-[15px]">
              {pendingQuestion}
            </div>
          </div>
          <div className="inline-flex max-w-full flex-col gap-2 rounded-2xl rounded-bl-md border border-[var(--border-card)] bg-[var(--bg-card)] px-3 py-2.5 text-sm text-[var(--text-secondary)] sm:max-w-[95%] sm:px-4 sm:py-3">
            <div className="inline-flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--accent)] opacity-60" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--accent)]" />
              </span>
              <span className="text-[var(--text-primary)]">
                {pendingStageLabel || "Analyzing…"}
              </span>
            </div>
            {pendingStageLabel ? (
              <p className="text-[11px] uppercase tracking-[0.12em] text-[var(--text-secondary)]">
                Live pipeline
              </p>
            ) : null}
          </div>
        </article>
      ) : null}
    </div>
  );
}
