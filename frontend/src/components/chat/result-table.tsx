"use client";

import { formatCell } from "@/lib/chart";

type ResultTableProps = {
  columns: string[];
  rows: Record<string, unknown>[];
};

export function ResultTable({ columns, rows }: ResultTableProps) {
  if (!columns.length || !rows.length) return null;

  return (
    <div className="animate-fade-in overflow-hidden rounded-xl border border-[var(--border-card)] bg-[var(--bg-card)]">
      <div className="flex items-center justify-between gap-3 border-b border-[var(--border-card)] bg-[var(--bg-card)] px-3 py-2.5 sm:px-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
          Result set
        </p>
        <p className="shrink-0 font-mono text-[11px] text-[var(--text-secondary)]">
          {rows.length} row{rows.length === 1 ? "" : "s"}
        </p>
      </div>
      <div className="max-h-[min(50vh,18rem)] overflow-auto overscroll-contain sm:max-h-64">
        <table className="w-full min-w-max border-collapse text-left text-[13px] sm:text-sm">
          <thead className="sticky top-0 z-[1] bg-[var(--bg-card)]">
            <tr>
              {columns.map((col) => (
                <th
                  key={col}
                  title={col}
                  className="max-w-[12rem] border-b border-[var(--border-card)] bg-[var(--bg-card)] px-3 py-2.5 font-mono text-[11px] font-medium uppercase tracking-wide text-[var(--text-secondary)] sm:max-w-[16rem] sm:px-4"
                >
                  <span className="block break-words normal-case tracking-normal">
                    {col}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr
                key={idx}
                className="border-b border-[var(--border-card)]/70 last:border-0 hover:bg-black/[0.015]"
              >
                {columns.map((col) => {
                  const formatted = formatCell(row[col]);
                  return (
                    <td
                      key={col}
                      title={formatted === "—" ? undefined : formatted}
                      className="max-w-[14rem] break-words px-3 py-2.5 align-top text-[var(--text-primary)] sm:max-w-[20rem] sm:px-4"
                    >
                      <span className="whitespace-pre-wrap">{formatted}</span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
