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
      <div className="flex items-center justify-between border-b border-[var(--border-card)] px-4 py-2.5">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">
          Result set
        </p>
        <p className="font-mono text-[11px] text-[var(--text-secondary)]">
          {rows.length} row{rows.length === 1 ? "" : "s"}
        </p>
      </div>
      <div className="max-h-64 overflow-auto">
        <table className="w-full min-w-max border-collapse text-left text-sm">
          <thead className="sticky top-0 bg-[var(--bg-surface)]">
            <tr>
              {columns.map((col) => (
                <th
                  key={col}
                  className="border-b border-[var(--border-card)] px-4 py-2.5 font-mono text-[11px] font-medium uppercase tracking-wide text-[var(--text-secondary)]"
                >
                  {col}
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
                {columns.map((col) => (
                  <td
                    key={col}
                    className="px-4 py-2.5 tabular-nums text-[var(--text-primary)]"
                  >
                    {formatCell(row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
