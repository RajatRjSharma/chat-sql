"use client";

import { useCallback, useEffect, useState } from "react";
import { AuthGate } from "@/components/auth/auth-gate";
import { ConnectForm } from "@/components/connect/connect-form";
import { SavedSources } from "@/components/connect/saved-sources";
import { UploadForm } from "@/components/connect/upload-form";
import { Workspace } from "@/components/workspace";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";
import {
  clearAuthSession,
  loadAuthSession,
  onAuthCleared,
  saveAuthSession,
  type AuthSession,
} from "@/lib/auth";
import {
  clearWorkspace,
  loadWorkspace,
  saveWorkspace,
  type PersistedWorkspace,
} from "@/lib/demo";
import type { DataSourceSummary } from "@/lib/types";

export function AnalystApp() {
  const [ready, setReady] = useState(false);
  const [auth, setAuth] = useState<AuthSession | null>(null);
  const [workspace, setWorkspace] = useState<PersistedWorkspace | null>(null);
  const [sources, setSources] = useState<DataSourceSummary[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(true);
  const [selectingId, setSelectingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [selectError, setSelectError] = useState<string | null>(null);

  const resetToSignedOut = useCallback(() => {
    clearWorkspace();
    setAuth(null);
    setWorkspace(null);
    setSources([]);
    setSelectError(null);
    setSelectingId(null);
    setDeletingId(null);
    setSourcesLoading(false);
  }, []);

  const refreshSources = useCallback(async () => {
    try {
      const list = await api.listSources();
      setSources(list);
    } catch (err) {
      // Session already invalidated by api layer — stay empty until login.
      if (err instanceof ApiError && err.status === 401) {
        setSources([]);
        return;
      }
      setSources([]);
    } finally {
      setSourcesLoading(false);
    }
  }, []);

  // Cookie death (401 → failed refresh) clears storage; sync React to AuthGate.
  useEffect(() => onAuthCleared(resetToSignedOut), [resetToSignedOut]);

  useEffect(() => {
    async function boot() {
      // Cookie session: probe /me when a profile cache exists, or once blindly
      // after hard refresh if cookies might still be valid.
      const stored = loadAuthSession();
      try {
        const user = await api.me();
        const session = {
          expiresAt: stored?.expiresAt ?? Date.now() + 30 * 60 * 1000,
          user,
        };
        saveAuthSession(session);
        setAuth(session);
        setWorkspace(loadWorkspace());
        await refreshSources();
      } catch {
        clearAuthSession();
        resetToSignedOut();
      }
      setReady(true);
    }
    void boot();
  }, [refreshSources, resetToSignedOut]);

  function handleAuthenticated(session: AuthSession) {
    saveAuthSession(session);
    setAuth(session);
    setWorkspace(null);
    clearWorkspace();
    setSourcesLoading(true);
    void refreshSources();
  }

  async function handleLogout() {
    try {
      await api.logout();
    } catch {
      /* ignore — always clear local session */
    }
    clearAuthSession();
    resetToSignedOut();
  }

  function openWorkspace(payload: {
    dataSourceId: string;
    dataSourceName: string;
    chunksEmbedded: number;
    tablesIndexed?: number | null;
    schemaIndexedAt?: string | null;
  }) {
    const next: PersistedWorkspace = {
      dataSourceId: payload.dataSourceId,
      dataSourceName: payload.dataSourceName,
      sessionId: null,
      chunksEmbedded: payload.chunksEmbedded,
      tablesIndexed: payload.tablesIndexed ?? null,
      schemaIndexedAt: payload.schemaIndexedAt ?? null,
    };
    saveWorkspace(next);
    setWorkspace(next);
    void refreshSources();
  }

  function handleConnected(payload: {
    dataSourceId: string;
    dataSourceName: string;
    chunksEmbedded: number;
    tablesIndexed: number | null;
    schemaIndexedAt: string | null;
  }) {
    openWorkspace(payload);
  }

  async function handleSelectSaved(source: DataSourceSummary) {
    setSelectError(null);
    setSelectingId(source.id);

    try {
      let chunks = source.chunks_embedded;
      let tablesIndexed = source.tables_indexed ?? null;
      let schemaIndexedAt = source.schema_indexed_at ?? null;
      if (chunks <= 0) {
        const embedded = await api.embedSchema(source.id);
        chunks = embedded.chunks_embedded;
        tablesIndexed = embedded.tables_indexed ?? null;
        schemaIndexedAt = embedded.indexed_at ?? null;
      }

      openWorkspace({
        dataSourceId: source.id,
        dataSourceName: source.name,
        chunksEmbedded: chunks,
        tablesIndexed,
        schemaIndexedAt,
      });
    } catch (err) {
      setSelectError(
        err instanceof ApiError
          ? err.detail
          : "Could not open this warehouse",
      );
    } finally {
      setSelectingId(null);
    }
  }

  async function handleDeleteSaved(source: DataSourceSummary) {
    setSelectError(null);
    setDeletingId(source.id);
    try {
      await api.deleteSource(source.id);
      await refreshSources();
    } catch (err) {
      setSelectError(
        err instanceof ApiError
          ? err.detail
          : "Could not remove this warehouse",
      );
    } finally {
      setDeletingId(null);
    }
  }

  function handleSessionChange(sessionId: string | null) {
    setWorkspace((prev) => {
      if (!prev) return prev;
      const next = { ...prev, sessionId };
      saveWorkspace(next);
      return next;
    });
  }

  function handleSchemaIndexChange(update: {
    chunksEmbedded: number;
    tablesIndexed: number | null;
    schemaIndexedAt: string | null;
  }) {
    setWorkspace((prev) => {
      if (!prev) return prev;
      const next = {
        ...prev,
        chunksEmbedded: update.chunksEmbedded,
        tablesIndexed: update.tablesIndexed,
        schemaIndexedAt: update.schemaIndexedAt,
      };
      saveWorkspace(next);
      return next;
    });
    void refreshSources();
  }

  function handleSwitchWarehouse() {
    clearWorkspace();
    setWorkspace(null);
    setSelectError(null);
    void refreshSources();
  }

  if (!ready) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-[var(--bg-shell)]">
        <div className="h-8 w-8 animate-pulse rounded-full bg-[var(--accent)]/40" />
      </div>
    );
  }

  if (!auth) {
    return <AuthGate onAuthenticated={handleAuthenticated} />;
  }

  if (workspace) {
    return (
      <Workspace
        dataSourceId={workspace.dataSourceId}
        dataSourceName={workspace.dataSourceName}
        chunksEmbedded={workspace.chunksEmbedded}
        tablesIndexed={workspace.tablesIndexed}
        schemaIndexedAt={workspace.schemaIndexedAt}
        sessionId={workspace.sessionId}
        onSessionChange={handleSessionChange}
        onSchemaIndexChange={handleSchemaIndexChange}
        onDisconnect={handleSwitchWarehouse}
        onLogout={() => void handleLogout()}
        userLabel={auth.user.username}
      />
    );
  }

  const busy = selectingId != null || deletingId != null;

  return (
    <div className="relative min-h-[100dvh] overflow-x-hidden bg-[var(--bg-shell)] text-[var(--text-on-dark)]">
      <div aria-hidden className="pointer-events-none absolute inset-0 mesh-grid opacity-40" />
      <div
        aria-hidden
        className="pointer-events-none absolute -left-24 top-24 h-72 w-72 rounded-full bg-[var(--accent)]/10 blur-3xl"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute bottom-0 right-0 h-96 w-96 rounded-full bg-[var(--accent-light)]/15 blur-3xl"
      />

      <div className="relative mx-auto flex min-h-[100dvh] max-w-6xl flex-col px-4 pb-[max(1.5rem,var(--safe-bottom))] pt-[max(1.5rem,var(--safe-top))] sm:px-5 sm:py-8 md:px-10 md:py-12">
        <header className="flex items-start justify-between gap-3 animate-fade-in sm:items-center">
          <div className="min-w-0">
            <p className="break-words font-[family-name:var(--font-display)] text-base leading-tight tracking-tight sm:text-xl md:text-2xl">
              Voice-Driven Data Analyst
            </p>
            <p className="mt-1 break-words text-sm text-[var(--text-muted-dark)]">
              @{auth.user.username}
            </p>
          </div>
          <Button
            variant="secondary"
            size="sm"
            className="shrink-0"
            onClick={() => void handleLogout()}
          >
            Log out
          </Button>
        </header>

        <div className="mt-8 grid flex-1 items-start gap-8 sm:mt-10 sm:gap-12 lg:mt-16 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
          <section className="min-w-0 animate-rise">
            <h1 className="max-w-xl font-[family-name:var(--font-display)] text-3xl leading-[1.05] tracking-tight sm:text-4xl md:text-5xl lg:text-[3.4rem]">
              Ask your warehouse.
            </h1>
            <p className="mt-4 max-w-md text-base leading-relaxed text-[var(--text-muted-dark)] sm:mt-5 sm:text-lg">
              Ask business questions. Get validated SQL, charts, and executive-ready
              answers from your warehouse.
            </p>
            <ol className="mt-8 space-y-4 text-sm text-[var(--text-muted-dark)] sm:mt-10">
              {[
                "Open a saved warehouse, connect one, or upload CSV/Excel",
                "Browse past sessions for that source",
                "Ask questions — follow-ups keep session memory",
              ].map((step, i) => (
                <li key={step} className="flex gap-3">
                  <span className="font-mono text-[var(--accent)]">0{i + 1}</span>
                  <span className="min-w-0">{step}</span>
                </li>
              ))}
            </ol>
          </section>

          <div className="min-w-0 space-y-5">
            <SavedSources
              sources={sources}
              loading={sourcesLoading}
              busy={busy}
              activeId={selectingId}
              deletingId={deletingId}
              onSelect={handleSelectSaved}
              onDelete={handleDeleteSaved}
            />

            {selectError ? (
              <p
                role="alert"
                className="break-words rounded-md border border-[var(--error)]/30 bg-[var(--error)]/10 px-3 py-2 text-sm text-[#fecaca]"
              >
                {selectError}
              </p>
            ) : null}

            {busy ? (
              <p className="break-words text-xs text-[var(--text-muted-dark)] animate-fade-in">
                Opening warehouse
                {sources.find((s) => s.id === selectingId)?.name
                  ? ` · ${sources.find((s) => s.id === selectingId)?.name}`
                  : ""}
                …
              </p>
            ) : null}

            <ConnectForm onConnected={handleConnected} />
            <UploadForm onUploaded={handleConnected} />
          </div>
        </div>
      </div>
    </div>
  );
}
