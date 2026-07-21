"use client";

import { useCallback, useEffect, useState } from "react";
import { ConnectForm } from "@/components/connect/connect-form";
import { SavedSources } from "@/components/connect/saved-sources";
import { UploadForm } from "@/components/connect/upload-form";
import { Workspace } from "@/components/workspace";
import { api, ApiError } from "@/lib/api";
import {
  clearWorkspace,
  loadWorkspace,
  saveWorkspace,
  type PersistedWorkspace,
} from "@/lib/demo";
import type { DataSourceSummary } from "@/lib/types";

export function AnalystApp() {
  const [ready, setReady] = useState(false);
  const [workspace, setWorkspace] = useState<PersistedWorkspace | null>(null);
  const [sources, setSources] = useState<DataSourceSummary[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(true);
  const [selectingId, setSelectingId] = useState<string | null>(null);
  const [selectError, setSelectError] = useState<string | null>(null);

  const refreshSources = useCallback(async () => {
    try {
      const list = await api.listSources();
      setSources(list);
    } catch {
      setSources([]);
    } finally {
      setSourcesLoading(false);
    }
  }, []);

  useEffect(() => {
    setWorkspace(loadWorkspace());
    setReady(true);
    void refreshSources();
  }, [refreshSources]);

  function openWorkspace(payload: {
    dataSourceId: string;
    dataSourceName: string;
    chunksEmbedded: number;
  }) {
    const next: PersistedWorkspace = {
      dataSourceId: payload.dataSourceId,
      dataSourceName: payload.dataSourceName,
      sessionId: null,
      chunksEmbedded: payload.chunksEmbedded,
    };
    saveWorkspace(next);
    setWorkspace(next);
    void refreshSources();
  }

  function handleConnected(payload: {
    dataSourceId: string;
    dataSourceName: string;
    chunksEmbedded: number;
  }) {
    openWorkspace(payload);
  }

  async function handleSelectSaved(source: DataSourceSummary) {
    setSelectError(null);
    setSelectingId(source.id);

    try {
      let chunks = source.chunks_embedded;
      if (chunks <= 0) {
        const embedded = await api.embedSchema(source.id);
        chunks = embedded.chunks_embedded;
      }

      openWorkspace({
        dataSourceId: source.id,
        dataSourceName: source.name,
        chunksEmbedded: chunks,
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

  function handleSessionChange(sessionId: string | null) {
    setWorkspace((prev) => {
      if (!prev) return prev;
      const next = { ...prev, sessionId };
      saveWorkspace(next);
      return next;
    });
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

  if (workspace) {
    return (
      <Workspace
        dataSourceId={workspace.dataSourceId}
        dataSourceName={workspace.dataSourceName}
        chunksEmbedded={workspace.chunksEmbedded}
        sessionId={workspace.sessionId}
        onSessionChange={handleSessionChange}
        onDisconnect={handleSwitchWarehouse}
      />
    );
  }

  const busy = selectingId != null;

  return (
    <div className="relative min-h-[100dvh] overflow-hidden bg-[var(--bg-shell)] text-[var(--text-on-dark)]">
      <div aria-hidden className="pointer-events-none absolute inset-0 mesh-grid opacity-40" />
      <div
        aria-hidden
        className="pointer-events-none absolute -left-24 top-24 h-72 w-72 rounded-full bg-[var(--accent)]/10 blur-3xl"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute bottom-0 right-0 h-96 w-96 rounded-full bg-[#1d4ed8]/10 blur-3xl"
      />

      <div className="relative mx-auto flex min-h-[100dvh] max-w-6xl flex-col px-5 py-8 md:px-10 md:py-12">
        <header className="flex items-center justify-between animate-fade-in">
          <div>
            <p className="font-[family-name:var(--font-display)] text-2xl tracking-tight md:text-3xl">
              Meridian
            </p>
            <p className="mt-1 text-sm text-[var(--text-muted-dark)]">
              Voice-Driven Data Analyst
            </p>
          </div>
          <p className="hidden text-xs uppercase tracking-[0.16em] text-[var(--text-muted-dark)] sm:block">
            Executive console
          </p>
        </header>

        <div className="mt-14 grid flex-1 items-start gap-12 lg:mt-16 lg:grid-cols-[1.05fr_0.95fr]">
          <section className="animate-rise">
            <h1 className="max-w-xl font-[family-name:var(--font-display)] text-4xl leading-[1.05] tracking-tight md:text-5xl lg:text-[3.4rem]">
              Meridian
            </h1>
            <p className="mt-5 max-w-md text-lg leading-relaxed text-[var(--text-muted-dark)]">
              Ask business questions. Get validated SQL, charts, and executive-ready
              answers from your warehouse.
            </p>
            <ol className="mt-10 space-y-4 text-sm text-[var(--text-muted-dark)]">
              {[
                "Open a saved warehouse, connect one, or upload CSV/Excel",
                "Browse past sessions for that source",
                "Ask questions — follow-ups keep session memory",
              ].map((step, i) => (
                <li key={step} className="flex gap-3">
                  <span className="font-mono text-[var(--accent)]">0{i + 1}</span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          </section>

          <div className="space-y-5">
            <SavedSources
              sources={sources}
              loading={sourcesLoading}
              busy={busy}
              activeId={selectingId}
              onSelect={handleSelectSaved}
            />

            {selectError ? (
              <p
                role="alert"
                className="rounded-md border border-[var(--error)]/30 bg-[var(--error)]/10 px-3 py-2 text-sm text-[#fecaca]"
              >
                {selectError}
              </p>
            ) : null}

            {busy ? (
              <p className="text-xs text-[var(--text-muted-dark)] animate-fade-in">
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
