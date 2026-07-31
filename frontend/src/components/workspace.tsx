"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Menu, X } from "lucide-react";
import { Composer } from "@/components/chat/composer";
import {
  InsightPanel,
  MobileInsightDrawer,
} from "@/components/chat/insight-panel";
import { prefetchSpeakText } from "@/lib/speak-playback";
import { MessageList } from "@/components/chat/message-list";
import { SessionHistory } from "@/components/chat/session-history";
import { Button } from "@/components/ui/button";
import { useMediaQuery } from "@/hooks/use-media-query";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { SUGGESTED_QUESTIONS } from "@/lib/demo";
import type { ChatTurn, SessionSummary, SuggestedQuestion } from "@/lib/types";

type WorkspaceProps = {
  dataSourceId: string;
  dataSourceName: string;
  chunksEmbedded: number | null;
  sessionId: string | null;
  onSessionChange: (sessionId: string | null) => void;
  onDisconnect: () => void;
  onLogout: () => void;
  userLabel: string;
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
  onLogout,
  userLabel,
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
  const [menuOpen, setMenuOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const hydratedSessionRef = useRef<string | null>(null);
  const isDesktop = useMediaQuery("(min-width: 1024px)");

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

  useEffect(() => {
    function onResize() {
      if (window.matchMedia("(min-width: 640px)").matches) {
        setMenuOpen(false);
      }
    }
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  async function ask(question: string) {
    setError(null);
    setDraft("");
    setPendingQuestion(question);
    setPendingStageLabel("Preparing session");
    setMenuOpen(false);

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
      setTurns((prev) => {
        const turnId = `${res.session_id}-${prev.length}-${Date.now()}`;
        if (res.status === "ok" && res.answer?.trim()) {
          prefetchSpeakText(res.answer);
        }
        return [
          ...prev,
          {
            id: turnId,
            question: res.question,
            answer: res.answer,
            sql: res.sql,
            columns: res.columns,
            rows: res.rows,
            status: res.status,
            attempts: res.attempts,
            source_metadata: res.source_metadata ?? null,
          },
        ];
      });
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
      const last = detail.turns[detail.turns.length - 1];
      if (last?.answer?.trim() && last.status !== "failed") {
        prefetchSpeakText(last.answer);
      }
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
    setMenuOpen(false);
    onSessionChange(null);
  }

  const latest = turns.length ? turns[turns.length - 1] : null;
  const busy = pendingQuestion != null || loadingSession;
  const suggestionTexts = suggestions.map((s) => s.question);

  return (
    <div className="flex h-[100dvh] max-h-[100dvh] min-h-0 flex-col overflow-hidden bg-[var(--bg-shell)] text-[var(--text-on-dark)]">
      <header className="relative z-20 shrink-0 border-b border-white/8 pt-[max(0px,var(--safe-top))]">
        <div className="safe-px flex items-center justify-between gap-3 px-3 py-3 sm:px-5 sm:py-3.5 md:px-7">
          <div className="min-w-0 flex-1">
            <p
              className="break-words font-[family-name:var(--font-display)] text-[15px] leading-tight tracking-tight sm:text-base md:text-lg"
              title="Voice-Driven Data Analyst"
            >
              <span className="sm:hidden">VD Analyst</span>
              <span className="hidden sm:inline">Voice-Driven Data Analyst</span>
            </p>
            <p
              className="mt-0.5 break-words text-[11px] leading-snug text-[var(--text-muted-dark)] sm:text-xs"
              title={`@${userLabel} · ${dataSourceName}`}
            >
              @{userLabel} · {dataSourceName}
              {sessionId ? (
                <span className="ml-1.5 inline font-mono text-[10px] opacity-80 sm:ml-2">
                  session {sessionId.slice(0, 8)}
                </span>
              ) : (
                <span className="ml-1.5 text-[10px] opacity-80 sm:ml-2">new chat</span>
              )}
            </p>
          </div>

          <div className="hidden items-center gap-2 sm:flex">
            <Button
              variant="secondary"
              size="sm"
              className="lg:hidden"
              disabled={busy}
              onClick={handleNewChat}
            >
              New chat
            </Button>
            <span className="hidden items-center gap-2 rounded-full border border-white/10 px-3 py-1 text-[11px] text-[var(--text-muted-dark)] md:inline-flex">
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]" />
              Live
            </span>
            <Button variant="secondary" size="sm" onClick={onDisconnect}>
              <span className="md:hidden">Switch</span>
              <span className="hidden md:inline">Switch warehouse</span>
            </Button>
            <Button variant="ghost" size="sm" onClick={onLogout}>
              Log out
            </Button>
          </div>

          <button
            type="button"
            className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-md border border-white/10 text-[var(--text-on-dark)] hover:bg-white/[0.04] sm:hidden"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>

        {menuOpen ? (
          <div className="max-h-[min(70dvh,520px)] overflow-y-auto overscroll-contain border-t border-white/8 bg-[var(--bg-shell-elevated)] px-3 py-3 sm:hidden animate-fade-in">
            <div className="flex flex-col gap-2">
              <Button
                variant="secondary"
                size="sm"
                className="min-h-11 w-full justify-start"
                disabled={busy}
                onClick={handleNewChat}
              >
                New chat
              </Button>
              <Button
                variant="secondary"
                size="sm"
                className="min-h-11 w-full justify-start"
                onClick={() => {
                  setMenuOpen(false);
                  onDisconnect();
                }}
              >
                Switch warehouse
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="min-h-11 w-full justify-start text-[var(--text-on-dark)]"
                onClick={() => {
                  setMenuOpen(false);
                  onLogout();
                }}
              >
                Log out
              </Button>
            </div>

            {sessions.length > 0 ? (
              <div className="mt-4 border-t border-white/8 pt-3">
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted-dark)]">
                  Recent chats
                </p>
                <ul className="space-y-1.5">
                  {sessions.slice(0, 8).map((session) => (
                    <li key={session.session_id}>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => {
                          setMenuOpen(false);
                          void handleSelectSession(session.session_id);
                        }}
                        className={cn(
                          "min-h-11 w-full rounded-lg border px-3 py-2.5 text-left text-[13px] leading-snug transition-colors disabled:opacity-40",
                          session.session_id === sessionId
                            ? "border-[var(--accent)]/40 bg-[var(--accent)]/10 text-[var(--text-on-dark)]"
                            : "border-white/8 text-[var(--text-muted-dark)] hover:bg-white/[0.04] hover:text-[var(--text-on-dark)]",
                        )}
                      >
                        <span className="line-clamp-2 break-words">
                          {session.title || "Untitled session"}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {suggestionTexts.length > 0 ? (
              <div className="mt-4 border-t border-white/8 pt-3">
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted-dark)]">
                  Suggested
                </p>
                <ul className="space-y-1.5">
                  {suggestionTexts.slice(0, 4).map((q) => (
                    <li key={q}>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => {
                          setMenuOpen(false);
                          void ask(q);
                        }}
                        className="min-h-11 w-full break-words rounded-lg border border-white/8 px-3 py-2.5 text-left text-[12px] leading-snug text-[var(--text-muted-dark)] hover:bg-white/[0.04] hover:text-[var(--text-on-dark)] disabled:opacity-40"
                      >
                        {q}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
      </header>

      <div className="grid min-h-0 min-w-0 flex-1 grid-cols-1 lg:grid-cols-[220px_minmax(0,1fr)_minmax(260px,300px)] xl:grid-cols-[240px_minmax(0,1fr)_minmax(300px,340px)]">
        <aside className="hidden min-h-0 min-w-0 flex-col border-r border-white/8 bg-[var(--bg-shell)] p-5 lg:flex">
          <SessionHistory
            sessions={sessions}
            activeSessionId={sessionId}
            loading={sessionsLoading}
            disabled={busy}
            onSelect={handleSelectSession}
            onNewChat={handleNewChat}
          />

          <div className="mt-6 min-h-0 border-t border-white/8 pt-5">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted-dark)]">
              Suggested
            </p>
            {suggestionsLoading ? (
              <p className="mt-3 text-[12px] text-[var(--text-muted-dark)]">
                Loading prompts…
              </p>
            ) : (
              <ul className="mt-3 max-h-[40vh] space-y-1.5 overflow-y-auto overscroll-contain">
                {suggestionTexts.map((q) => (
                  <li key={q}>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => ask(q)}
                      className="w-full break-words rounded-lg border border-transparent px-3 py-2 text-left text-[12px] leading-snug text-[var(--text-muted-dark)] transition-colors hover:border-white/10 hover:bg-white/[0.04] hover:text-[var(--text-on-dark)] disabled:opacity-40"
                    >
                      {q}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>

        <main className="flex min-h-0 min-w-0 flex-col bg-[var(--bg-surface)] text-[var(--text-primary)]">
          <div
            ref={scrollRef}
            className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-contain px-3 py-4 sm:px-4 sm:py-6 md:px-8"
          >
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

          <div
            className={cn(
              "shrink-0 space-y-3 border-t border-[var(--border-card)] bg-[var(--bg-surface)]",
              "px-3 py-3 sm:px-4 sm:py-4 md:px-8",
              "pb-[max(0.75rem,env(safe-area-inset-bottom))]",
            )}
          >
            {error ? (
              <p
                role="alert"
                className="break-words rounded-md border border-[var(--error)]/25 bg-[var(--error)]/5 px-3 py-2 text-sm text-[var(--error)]"
              >
                {error}
              </p>
            ) : null}

            {!isDesktop ? (
              <MobileInsightDrawer
                latest={latest}
                dataSourceName={dataSourceName}
                chunksEmbedded={chunksEmbedded}
              />
            ) : null}

            {sessions.length > 0 ? (
              <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 [scrollbar-width:none] lg:hidden [&::-webkit-scrollbar]:hidden">
                {sessions.slice(0, 6).map((session) => {
                  const title = session.title || "Session";
                  return (
                    <button
                      key={session.session_id}
                      type="button"
                      disabled={busy}
                      title={title}
                      onClick={() => handleSelectSession(session.session_id)}
                      className={
                        session.session_id === sessionId
                          ? "min-h-11 max-w-[min(80vw,280px)] shrink-0 whitespace-normal break-words rounded-2xl border border-[var(--accent)] bg-[var(--accent-soft)] px-3 py-2 text-left text-xs leading-snug text-[var(--accent-hover)] disabled:opacity-40"
                          : "min-h-11 max-w-[min(80vw,280px)] shrink-0 whitespace-normal break-words rounded-2xl border border-[var(--border-card)] bg-[var(--bg-card)] px-3 py-2 text-left text-xs leading-snug text-[var(--text-secondary)] disabled:opacity-40"
                      }
                    >
                      {title}
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 [scrollbar-width:none] lg:hidden [&::-webkit-scrollbar]:hidden">
                {suggestionTexts.slice(0, 3).map((q) => (
                  <button
                    key={q}
                    type="button"
                    disabled={busy}
                    title={q}
                    onClick={() => ask(q)}
                    className="min-h-11 max-w-[min(80vw,280px)] shrink-0 whitespace-normal break-words rounded-2xl border border-[var(--border-card)] bg-[var(--bg-card)] px-3 py-2 text-left text-xs leading-snug text-[var(--text-secondary)] disabled:opacity-40"
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

        {isDesktop ? (
          <div className="min-h-0 min-w-0">
            <InsightPanel
              latest={latest}
              dataSourceName={dataSourceName}
              chunksEmbedded={chunksEmbedded}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}
