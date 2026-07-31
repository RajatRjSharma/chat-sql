"use client";

import { Menu, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import type { SessionSummary } from "@/lib/types";

type WorkspaceHeaderProps = {
  userLabel: string;
  dataSourceName: string;
  sessionId: string | null;
  menuOpen: boolean;
  setMenuOpen: (open: boolean | ((prev: boolean) => boolean)) => void;
  busy: boolean;
  onNewChat: () => void;
  onDisconnect: () => void;
  onLogout: () => void;
  sessions: SessionSummary[];
  onSelectSession: (sessionId: string) => void;
  suggestionTexts: string[];
  onAsk: (question: string) => void;
};

export function WorkspaceHeader({
  userLabel,
  dataSourceName,
  sessionId,
  menuOpen,
  setMenuOpen,
  busy,
  onNewChat,
  onDisconnect,
  onLogout,
  sessions,
  onSelectSession,
  suggestionTexts,
  onAsk,
}: WorkspaceHeaderProps) {
  return (
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
            onClick={onNewChat}
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
          <Button
            variant="ghost"
            size="sm"
            className="text-[var(--text-on-dark)] hover:bg-white/[0.06] hover:text-[var(--text-on-dark)]"
            onClick={onLogout}
          >
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
              onClick={onNewChat}
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
                        void onSelectSession(session.session_id);
                      }}
                      className={cn(
                        "min-h-11 w-full rounded-lg border px-3 py-2.5 text-left text-[13px] leading-snug transition-colors disabled:opacity-40",
                        session.session_id === sessionId
                          ? "border-[var(--accent)]/40 bg-[var(--accent)]/10 text-[var(--text-on-dark)]"
                          : "border-white/8 text-[var(--text-on-dark)]/90 hover:bg-white/[0.04] hover:text-[var(--text-on-dark)]",
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
                        void onAsk(q);
                      }}
                      className="min-h-11 w-full break-words rounded-lg border border-white/8 px-3 py-2.5 text-left text-[12px] leading-snug text-[var(--text-on-dark)]/90 hover:bg-white/[0.04] hover:text-[var(--text-on-dark)] disabled:opacity-40"
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
  );
}
