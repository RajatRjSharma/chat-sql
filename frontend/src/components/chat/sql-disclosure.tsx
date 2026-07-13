"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/cn";

type SqlDisclosureProps = {
  sql: string | null;
  attempts?: number;
};

export function SqlDisclosure({ sql, attempts }: SqlDisclosureProps) {
  const [open, setOpen] = useState(false);
  if (!sql) return null;

  return (
    <div className="rounded-xl border border-[var(--border-card)] bg-[var(--bg-card)]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left transition-colors hover:bg-black/[0.02]"
        aria-expanded={open}
      >
        <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
          Generated SQL
          {attempts && attempts > 1 ? (
            <span className="ml-2 font-mono normal-case tracking-normal text-[var(--text-secondary)]/80">
              · {attempts} attempts
            </span>
          ) : null}
        </span>
        <ChevronDown
          className={cn(
            "h-4 w-4 text-[var(--text-secondary)] transition-transform duration-200",
            open && "rotate-180",
          )}
        />
      </button>
      {open ? (
        <pre className="overflow-x-auto border-t border-[var(--border-card)] bg-[var(--bg-shell)] px-4 py-3 font-mono text-[12px] leading-relaxed text-[var(--text-on-dark)]">
          {sql}
        </pre>
      ) : null}
    </div>
  );
}
