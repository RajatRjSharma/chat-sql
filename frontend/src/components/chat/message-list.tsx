"use client";

import dynamic from "next/dynamic";
import { ResultTable } from "@/components/chat/result-table";
import { SqlDisclosure } from "@/components/chat/sql-disclosure";
import type { ChatTurn } from "@/lib/types";
import { cn } from "@/lib/cn";

const ResultChart = dynamic(
  () =>
    import("@/components/chat/result-chart").then((m) => m.ResultChart),
  {
    ssr: false,
    loading: () => (
      <div className="h-[180px] animate-pulse rounded-xl border border-[var(--border-card)] bg-[var(--bg-card)]" />
    ),
  },
);

type MessageListProps = {
  turns: ChatTurn[];
  pendingQuestion: string | null;
};

export function MessageList({ turns, pendingQuestion }: MessageListProps) {
  if (!turns.length && !pendingQuestion) {
    return (
      <div className="flex h-full min-h-[280px] flex-col items-center justify-center px-6 text-center animate-fade-in">
        <p className="font-[family-name:var(--font-display)] text-3xl tracking-tight text-[var(--text-primary)]">
          Ask anything about the warehouse
        </p>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-[var(--text-secondary)]">
          Questions become validated SQL, executed read-only, then summarized with a
          chart when the result shape allows.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {turns.map((turn) => (
        <article key={turn.id} className="space-y-4 animate-rise">
          <div className="flex justify-end">
            <div className="max-w-[85%] rounded-2xl rounded-br-md bg-[var(--bg-user)] px-4 py-3 text-[15px] leading-relaxed text-[var(--text-primary)]">
              {turn.question}
            </div>
          </div>

          <div className="max-w-[95%] space-y-3">
            <div
              className={cn(
                "rounded-2xl rounded-bl-md border px-4 py-3 text-[15px] leading-relaxed",
                turn.status === "failed"
                  ? "border-[var(--error)]/25 bg-[var(--error)]/5 text-[var(--error)]"
                  : "border-[var(--border-card)] bg-[var(--bg-card)] text-[var(--text-primary)] shadow-[0_1px_0_rgba(15,23,42,0.04)]",
              )}
            >
              {turn.answer}
            </div>

            {turn.status === "ok" && turn.rows.length > 0 ? (
              <>
                <ResultChart columns={turn.columns} rows={turn.rows} compact />
                <ResultTable columns={turn.columns} rows={turn.rows} />
              </>
            ) : null}

            <SqlDisclosure sql={turn.sql} attempts={turn.attempts} />
          </div>
        </article>
      ))}

      {pendingQuestion ? (
        <article className="space-y-4 animate-rise">
          <div className="flex justify-end">
            <div className="max-w-[85%] rounded-2xl rounded-br-md bg-[var(--bg-user)] px-4 py-3 text-[15px] leading-relaxed text-[var(--text-primary)]">
              {pendingQuestion}
            </div>
          </div>
          <div className="inline-flex items-center gap-2 rounded-2xl rounded-bl-md border border-[var(--border-card)] bg-[var(--bg-card)] px-4 py-3 text-sm text-[var(--text-secondary)]">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--accent)] opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--accent)]" />
            </span>
            Analyzing…
          </div>
        </article>
      ) : null}
    </div>
  );
}
