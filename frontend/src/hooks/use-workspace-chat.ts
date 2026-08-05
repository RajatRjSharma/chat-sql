"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { prefetchSpeakText } from "@/lib/speak-playback";
import { api, ApiError } from "@/lib/api";
import { SUGGESTED_QUESTIONS } from "@/lib/demo";
import type { ChatTurn, SessionSummary, SuggestedQuestion } from "@/lib/types";

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

type UseWorkspaceChatArgs = {
  dataSourceId: string;
  sessionId: string | null;
  onSessionChange: (sessionId: string | null) => void;
};

export function useWorkspaceChat({
  dataSourceId,
  sessionId,
  onSessionChange,
}: UseWorkspaceChatArgs) {
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

  return {
    turns,
    draft,
    setDraft,
    pendingQuestion,
    pendingStageLabel,
    loadingSession,
    sessions,
    sessionsLoading,
    suggestionsLoading,
    error,
    menuOpen,
    setMenuOpen,
    scrollRef,
    ask,
    handleSelectSession,
    handleNewChat,
    latest,
    busy,
    suggestionTexts,
    refreshSuggestions,
  };
}
