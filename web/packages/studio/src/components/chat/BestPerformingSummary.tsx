// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Gauge, Hash, Timer } from 'lucide-react';
import type { FC } from 'react';

/** Gold used for the "best performing" crown badges (matches the experiment view). */
export const CROWN_COLOR_CLASS = 'text-[#eaa83c]';

/** The three performance dimensions a model column can win. */
export interface WinnerStats {
  totalMs: number;
  tokensPerSec: number;
  completionTokens: number;
}

/** The winning model id for each performance dimension. */
export interface Winners {
  fastest: number;
  throughput: number;
  concise: number;
}

/** The performance dimensions surfaced in the "Best Performing" summary. */
export const WINNER_ROWS: { key: keyof Winners; label: string }[] = [
  { key: 'fastest', label: 'Speed' },
  { key: 'throughput', label: 'Throughput' },
  { key: 'concise', label: 'Conciseness' },
];

/**
 * Per-stat "winner" — the entry with the best value for each green stat. Only
 * returns a result when at least two entries are present, since a winner is
 * only meaningful as a comparison. Lower time wins (fastest), higher tokens/sec
 * wins (throughput), fewer completion tokens wins (most concise).
 */
export function computeWinners(entries: { id: number; stats: WinnerStats }[]): Winners | null {
  if (entries.length < 2) return null;
  const fastest = entries.reduce((b, e) => (e.stats.totalMs < b.stats.totalMs ? e : b));
  const throughput = entries.reduce((b, e) =>
    e.stats.tokensPerSec > b.stats.tokensPerSec ? e : b
  );
  const concise = entries.reduce((b, e) =>
    e.stats.completionTokens < b.stats.completionTokens ? e : b
  );
  return { fastest: fastest.id, throughput: throughput.id, concise: concise.id };
}

/**
 * Per-metric icon + value formatter for the performance summaries. Keyed by the
 * same winner dimensions as {@link WINNER_ROWS} (which supplies the labels), so
 * the Run Prompts footer and the Compare panel render identical values.
 */
export const FOOTER_METRIC_BY_KEY: Record<
  keyof Winners,
  { Icon: typeof Timer; title: string; format: (stats: WinnerStats) => string }
> = {
  fastest: {
    Icon: Timer,
    title: 'Total time',
    format: (s) => `${(s.totalMs / 1000).toFixed(1)}s`,
  },
  throughput: {
    Icon: Gauge,
    title: 'Tokens per second',
    format: (s) => `${Math.max(0, Math.round(s.tokensPerSec))} t/s`,
  },
  concise: {
    Icon: Hash,
    title: 'Completion tokens',
    format: (s) => `${s.completionTokens} tok`,
  },
};

/**
 * A single metric value (icon + formatted number). Brand green when it's the
 * metric winner, foreground otherwise. Shared by the Run Prompts footer and the
 * Compare performance panel so the two presentations stay in sync.
 */
export const MetricValue: FC<{
  stats: WinnerStats;
  metricKey: keyof Winners;
  highlight: boolean;
  className?: string;
}> = ({ stats, metricKey, highlight, className }) => {
  const metric = FOOTER_METRIC_BY_KEY[metricKey];
  return (
    <span
      className={`inline-flex items-center gap-1 font-mono text-xs ${
        highlight ? 'text-[var(--color-brand)]' : 'text-fg-base'
      } ${className ?? ''}`}
      title={metric.title}
    >
      <metric.Icon size={12} />
      {metric.format(stats)}
    </span>
  );
};
