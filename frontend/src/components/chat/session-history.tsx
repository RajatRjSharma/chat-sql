"use client";

import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import type { SessionSummary } from "@/lib/types";

type SessionHistoryProps = {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  loading?: boolean;
  disabled?: boolean;
  onSelect: (sessionId: string) => void;
  onNewChat: () => void;
};

function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diffMs = Date.now() - then;
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

export function SessionHistory({
  sessions,
  activeSessionId,
  loading,
  disabled,
  onSelect,
  onNewChat,
}: SessionHistoryProps) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted-dark)]">
          History
        </p>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          className="h-8 px-2.5 text-[11px]"
          disabled={disabled}
          onClick={onNewChat}
        >
          <Plus className="h-3.5 w-3.5" />
          New
        </Button>
      </div>

      <div className="mt-3 min-h-0 flex-1 overflow-y-auto pr-1">
        {loading && sessions.length === 0 ? (
          <p className="px-1 text-xs text-[var(--text-muted-dark)]">Loading…</p>
        ) : null}

        {!loading && sessions.length === 0 ? (
          <p className="px-1 text-xs leading-relaxed text-[var(--text-muted-dark)]">
            Ask a question to start a session. Past chats for this warehouse will
            appear here.
          </p>
        ) : null}

        <ul className="space-y-1">
          {sessions.map((session) => {
            const active = session.session_id === activeSessionId;
            return (
              <li key={session.session_id}>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => onSelect(session.session_id)}
                  className={cn(
                    "w-full rounded-lg border px-3 py-2.5 text-left transition-colors",
                    "disabled:opacity-40",
                    active
                      ? "border-[var(--accent)]/40 bg-[var(--accent)]/10 text-[var(--text-on-dark)]"
                      : "border-transparent text-[var(--text-muted-dark)] hover:border-white/10 hover:bg-white/[0.04] hover:text-[var(--text-on-dark)]",
                  )}
                >
                  <span className="line-clamp-2 text-[13px] leading-snug">
                    {session.title || "Untitled session"}
                  </span>
                  <span className="mt-1.5 flex items-center justify-between gap-2 font-mono text-[10px] opacity-70">
                    <span>
                      {session.message_count} msg
                      {session.message_count === 1 ? "" : "s"}
                    </span>
                    <span>{formatRelative(session.updated_at)}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
