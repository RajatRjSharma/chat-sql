"use client";

import { useState } from "react";
import {
  chartSeriesIdentity,
  deriveChart,
  type ChartDisplayKind,
} from "@/lib/chart";
import { useMediaQuery } from "@/hooks/use-media-query";
import { ChartFullscreenModal } from "./chart-fullscreen";
import { ChartShell } from "./chart-shell";

type ResultChartProps = {
  columns: string[];
  rows: Record<string, unknown>[];
  compact?: boolean;
};

export function ResultChart({ columns, rows, compact = false }: ResultChartProps) {
  const series = deriveChart(columns, rows);
  const identity = chartSeriesIdentity(series);
  const [pickedKind, setPickedKind] = useState<ChartDisplayKind | null>(null);
  const [baselineIdentity, setBaselineIdentity] = useState(identity);
  const [fullscreen, setFullscreen] = useState(false);
  const isNarrow = useMediaQuery("(max-width: 639px)");

  if (identity !== baselineIdentity) {
    setBaselineIdentity(identity);
    setPickedKind(null);
  }

  if (series.kind === "none") return null;

  const activeKind: ChartDisplayKind = pickedKind ?? series.kind;
  const showTruncationNote =
    series.valueKey !== "count" && rows.length > series.data.length;

  // Responsive heights: taller on phones when pie stacks; room for axis labels on bar/line.
  const height =
    activeKind === "pie"
      ? isNarrow
        ? compact
          ? 420
          : 460
        : compact
          ? 330
          : 380
      : isNarrow
        ? compact
          ? 260
          : 300
        : compact
          ? 240
          : 320;

  return (
    <>
      <ChartShell
        series={series}
        activeKind={activeKind}
        onKindChange={setPickedKind}
        height={height}
        compact={compact}
        showTruncationNote={showTruncationNote}
        rowCount={rows.length}
        onExpand={() => setFullscreen(true)}
      />
      {fullscreen ? (
        <ChartFullscreenModal
          series={series}
          activeKind={activeKind}
          onKindChange={setPickedKind}
          showTruncationNote={showTruncationNote}
          rowCount={rows.length}
          onClose={() => setFullscreen(false)}
        />
      ) : null}
    </>
  );
}
