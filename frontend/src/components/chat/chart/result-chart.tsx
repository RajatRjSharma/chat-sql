"use client";

import { useState } from "react";
import {
  availableChartKinds,
  chartSeriesIdentity,
  chartVisibleCount,
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

  const kindOptions = availableChartKinds(series);
  const fallbackKind = kindOptions.includes(series.kind as ChartDisplayKind)
    ? (series.kind as ChartDisplayKind)
    : kindOptions[0];
  const activeKind: ChartDisplayKind =
    pickedKind && kindOptions.includes(pickedKind) ? pickedKind : fallbackKind;
  const visible = chartVisibleCount(series);
  const showTruncationNote =
    series.valueKey !== "count" &&
    series.family !== "heatmap" &&
    rows.length > visible;

  // Responsive heights: header is two rows; pie/heatmap/multi need extra plot room.
  const height =
    activeKind === "pie"
      ? isNarrow
        ? compact
          ? 440
          : 480
        : compact
          ? 350
          : 400
      : activeKind === "heatmap"
        ? isNarrow
          ? compact
            ? 340
            : 400
          : compact
            ? 320
            : 380
        : series.family === "multi"
          ? isNarrow
            ? compact
              ? 320
              : 360
            : compact
              ? 310
              : 370
          : activeKind === "scatter"
            ? isNarrow
              ? compact
                ? 300
                : 340
              : compact
                ? 290
                : 350
            : isNarrow
              ? compact
                ? 290
                : 330
              : compact
                ? 280
                : 350;

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
