"use client";

import { Composer } from "@/components/chat/composer";
import {
  InsightPanel,
  MobileInsightDrawer,
} from "@/components/chat/insight-panel";
import { MessageList } from "@/components/chat/message-list";
import { SessionHistory } from "@/components/chat/session-history";
import { WorkspaceHeader } from "@/components/workspace/workspace-header";
import { useMediaQuery } from "@/hooks/use-media-query";
import { useWorkspaceChat } from "@/hooks/use-workspace-chat";
import { cn } from "@/lib/cn";

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
  const isDesktop = useMediaQuery("(min-width: 1024px)");
  const {
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
    busy,
    suggestionTexts,
  } = useWorkspaceChat({
    dataSourceId,
    sessionId,
    onSessionChange,
  });

  return (
    <div className="flex h-[100dvh] max-h-[100dvh] min-h-0 flex-col overflow-hidden bg-[var(--bg-shell)] text-[var(--text-on-dark)]">
      <WorkspaceHeader
        userLabel={userLabel}
        dataSourceName={dataSourceName}
        sessionId={sessionId}
        menuOpen={menuOpen}
        setMenuOpen={setMenuOpen}
        busy={busy}
        onNewChat={handleNewChat}
        onDisconnect={onDisconnect}
        onLogout={onLogout}
        sessions={sessions}
        onSelectSession={handleSelectSession}
        suggestionTexts={suggestionTexts}
        onAsk={ask}
      />

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
                      className="w-full break-words rounded-lg border border-transparent px-3 py-2 text-left text-[12px] leading-snug text-[var(--text-on-dark)]/90 transition-colors hover:border-white/10 hover:bg-white/[0.04] hover:text-[var(--text-on-dark)] disabled:opacity-40"
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
                turns={turns}
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
              turns={turns}
              dataSourceName={dataSourceName}
              chunksEmbedded={chunksEmbedded}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}
