"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Composer } from "@/components/chat/composer";
import { InsightPanel } from "@/components/chat/insight-panel";
import { MessageList } from "@/components/chat/message-list";
import { SessionHistory } from "@/components/chat/session-history";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";
import { SUGGESTED_QUESTIONS } from "@/lib/demo";
import type { ChatTurn, SessionSummary, SuggestedQuestion } from "@/lib/types";

type WorkspaceProps = {
  dataSourceId: string;
  dataSourceName: string;
  chunksEmbedded: number | null;
  sessionId: string | null;
  onSessionChange: (sessionId: string | null) => void;
  onDisconnect: () => void;
};

function turnsFromDetail(
  sessionId: string,
  turns: {
    question: string;
    answer: string;
    sql: string | null;
    columns: string[];
    rows: Record<string, unknown>[];
    status: ChatTurn["status"];
    attempts: number;
    source_metadata?: ChatTurn["source_metadata"];
  }[],
): ChatTurn[] {
  return turns.map((turn, index) => ({
    id: `${sessionId}-${index}`,
    question: turn.question,
    answer: turn.answer,
    sql: turn.sql,
    columns: turn.columns,
    rows: turn.rows,
    status: turn.status,
    attempts: turn.attempts,
    source_metadata: turn.source_metadata ?? null,
  }));
}

function fallbackSuggestions(): SuggestedQuestion[] {
  return SUGGESTED_QUESTIONS.map((question) => ({
    question,
    source: "fallback" as const,
    table: null,
  }));
}

export function Workspace({
  dataSourceId,
  dataSourceName,
  chunksEmbedded,
  sessionId,
  onSessionChange,
  onDisconnect,
}: WorkspaceProps) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [pendingStageLabel, setPendingStageLabel] = useState<string | null>(null);
  const [loadingSession, setLoadingSession] = useState(false);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [suggestions, setSuggestions] = useState<SuggestedQuestion[]>(
    fallbackSuggestions,
  );
  const [suggestionsLoading, setSuggestionsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const hydratedSessionRef = useRef<string | null>(null);

  const refreshSessions = useCallback(async () => {
    try {
      const list = await api.listSessions(dataSourceId);
      setSessions(list);
    } catch {
      // History is secondary — don't block the workspace on list failures.
    } finally {
      setSessionsLoading(false);
    }
  }, [dataSourceId]);

  const refreshSuggestions = useCallback(async () => {
    setSuggestionsLoading(true);
    try {
      const res = await api.suggestedQuestions(dataSourceId);
      if (res.suggestions.length > 0) {
        setSuggestions(res.suggestions);
      } else {
        setSuggestions(fallbackSuggestions());
      }
    } catch {
      setSuggestions(fallbackSuggestions());
    } finally {
      setSuggestionsLoading(false);
    }
  }, [dataSourceId]);

  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

  useEffect(() => {
    void refreshSuggestions();
  }, [refreshSuggestions]);

  useEffect(() => {
    if (!sessionId) {
      hydratedSessionRef.current = null;
      return;
    }
    if (hydratedSessionRef.current === sessionId && turns.length > 0) {
      return;
    }

    let cancelled = false;

    async function load() {
      setLoadingSession(true);
      setError(null);
      try {
        const detail = await api.getSession(sessionId!);
        if (cancelled) return;
        setTurns(turnsFromDetail(detail.session_id, detail.turns));
        hydratedSessionRef.current = detail.session_id;
      } catch (err) {
        if (cancelled) return;
        setError(
          err instanceof ApiError ? err.detail : "Could not load session",
        );
      } finally {
        if (!cancelled) setLoadingSession(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
    // Only auto-hydrate when sessionId changes from persistence / selection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [turns, pendingQuestion, pendingStageLabel, loadingSession]);

  async function ask(question: string) {
    setError(null);
    setDraft("");
    setPendingQuestion(question);
    setPendingStageLabel("Preparing session");

    try {
      const res = await api.chatStream(
        {
          data_source_id: dataSourceId,
          question,
          session_id: sessionId,
        },
        (event) => {
          if (event.type === "stage") {
            setPendingStageLabel(event.label);
          }
        },
      );

      hydratedSessionRef.current = res.session_id;
      onSessionChange(res.session_id);
      setTurns((prev) => [
        ...prev,
        {
          id: `${res.session_id}-${prev.length}-${Date.now()}`,
          question: res.question,
          answer: res.answer,
          sql: res.sql,
          columns: res.columns,
          rows: res.rows,
          status: res.status,
          attempts: res.attempts,
          source_metadata: res.source_metadata ?? null,
        },
      ]);
      void refreshSessions();
      void refreshSuggestions();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Chat request failed");
    } finally {
      setPendingQuestion(null);
      setPendingStageLabel(null);
    }
  }

  async function handleSelectSession(nextId: string) {
    if (nextId === sessionId || pendingQuestion || loadingSession) return;
    setError(null);
    setLoadingSession(true);
    try {
      const detail = await api.getSession(nextId);
      setTurns(turnsFromDetail(detail.session_id, detail.turns));
      hydratedSessionRef.current = detail.session_id;
      onSessionChange(detail.session_id);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not load session");
    } finally {
      setLoadingSession(false);
    }
  }

  function handleNewChat() {
    hydratedSessionRef.current = null;
    setTurns([]);
    setDraft("");
    setError(null);
    onSessionChange(null);
  }

  const latest = turns.length ? turns[turns.length - 1] : null;
  const busy = pendingQuestion != null || loadingSession;
  const suggestionTexts = suggestions.map((s) => s.question);

  return (
    <div className="flex h-[100dvh] flex-col bg-[var(--bg-shell)] text-[var(--text-on-dark)]">
      <header className="flex shrink-0 items-center justify-between gap-4 border-b border-white/8 px-5 py-3.5 md:px-7">
        <div className="min-w-0">
          <p className="font-[family-name:var(--font-display)] text-lg tracking-tight md:text-xl">
            Meridian
          </p>
          <p className="truncate text-xs text-[var(--text-muted-dark)]">
            Executive intelligence · {dataSourceName}
            {sessionId ? (
              <span className="ml-2 font-mono text-[10px] opacity-80">
                session {sessionId.slice(0, 8)}
              </span>
            ) : (
              <span className="ml-2 text-[10px] opacity-80">new chat</span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            className="lg:hidden"
            disabled={busy}
            onClick={handleNewChat}
          >
            New chat
          </Button>
          <span className="hidden items-center gap-2 rounded-full border border-white/10 px-3 py-1 text-[11px] text-[var(--text-muted-dark)] sm:inline-flex">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]" />
            Live
          </span>
          <Button variant="secondary" size="sm" onClick={onDisconnect}>
            Switch warehouse
          </Button>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[240px_minmax(0,1fr)_320px]">
        <aside className="hidden min-h-0 flex-col border-r border-white/8 bg-[var(--bg-shell)] p-5 lg:flex">
          <SessionHistory
            sessions={sessions}
            activeSessionId={sessionId}
            loading={sessionsLoading}
            disabled={busy}
            onSelect={handleSelectSession}
            onNewChat={handleNewChat}
          />

          <div className="mt-6 border-t border-white/8 pt-5">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted-dark)]">
              Suggested
            </p>
            {suggestionsLoading ? (
              <p className="mt-3 text-[12px] text-[var(--text-muted-dark)]">
                Loading prompts…
              </p>
            ) : (
              <ul className="mt-3 space-y-1.5">
                {suggestionTexts.map((q) => (
                  <li key={q}>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => ask(q)}
                      className="w-full rounded-lg border border-transparent px-3 py-2 text-left text-[12px] leading-snug text-[var(--text-muted-dark)] transition-colors hover:border-white/10 hover:bg-white/[0.04] hover:text-[var(--text-on-dark)] disabled:opacity-40"
                    >
                      {q}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>

        <main className="flex min-h-0 flex-col bg-[var(--bg-surface)] text-[var(--text-primary)]">
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6 md:px-8">
            {loadingSession && turns.length === 0 ? (
              <div className="flex min-h-[240px] items-center justify-center text-sm text-[var(--text-secondary)]">
                Loading session…
              </div>
            ) : (
              <MessageList
                turns={turns}
                pendingQuestion={pendingQuestion}
                pendingStageLabel={pendingStageLabel}
              />
            )}
          </div>

          <div className="shrink-0 space-y-3 border-t border-[var(--border-card)] bg-[var(--bg-surface)] px-4 py-4 md:px-8">
            {error ? (
              <p
                role="alert"
                className="rounded-md border border-[var(--error)]/25 bg-[var(--error)]/5 px-3 py-2 text-sm text-[var(--error)]"
              >
                {error}
              </p>
            ) : null}

            {sessions.length > 0 ? (
              <div className="flex gap-2 overflow-x-auto pb-1 lg:hidden">
                {sessions.slice(0, 6).map((session) => (
                  <button
                    key={session.session_id}
                    type="button"
                    disabled={busy}
                    onClick={() => handleSelectSession(session.session_id)}
                    className={
                      session.session_id === sessionId
                        ? "shrink-0 rounded-full border border-[var(--accent)] bg-[var(--accent-soft)] px-3 py-1.5 text-xs text-[var(--accent-hover)] disabled:opacity-40"
                        : "shrink-0 rounded-full border border-[var(--border-card)] bg-[var(--bg-card)] px-3 py-1.5 text-xs text-[var(--text-secondary)] disabled:opacity-40"
                    }
                  >
                    {(session.title || "Session").slice(0, 28)}
                  </button>
                ))}
              </div>
            ) : (
              <div className="flex gap-2 overflow-x-auto pb-1 lg:hidden">
                {suggestionTexts.slice(0, 2).map((q) => (
                  <button
                    key={q}
                    type="button"
                    disabled={busy}
                    onClick={() => ask(q)}
                    className="shrink-0 rounded-full border border-[var(--border-card)] bg-[var(--bg-card)] px-3 py-1.5 text-xs text-[var(--text-secondary)] disabled:opacity-40"
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}

            <Composer
              value={draft}
              onChange={setDraft}
              onSubmit={ask}
              disabled={busy}
            />
          </div>
        </main>

        <div className="hidden min-h-0 lg:block">
          <InsightPanel
            latest={latest}
            dataSourceName={dataSourceName}
            chunksEmbedded={chunksEmbedded}
          />
        </div>
      </div>
    </div>
  );
}
