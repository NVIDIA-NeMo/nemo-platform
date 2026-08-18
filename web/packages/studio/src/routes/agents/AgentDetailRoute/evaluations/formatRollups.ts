// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AgentEvaluationRow } from '@studio/routes/agents/AgentDetailRoute/useAgentDetails';

/** Rollups are computed from ingested telemetry, so every one is absent until a run publishes. */
export const formatScore = (value: number | null | undefined): string =>
  typeof value === 'number' ? value.toFixed(2) : '—';

export const formatLatency = (ms: number | null | undefined): string =>
  typeof ms !== 'number' ? '—' : ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;

export const formatCost = (usd: number | null | undefined): string =>
  typeof usd !== 'number' ? '—' : `$${usd < 0.01 ? usd.toFixed(4) : usd.toFixed(2)}`;

/** Evaluator keys arrive as ``<metric-type>.<score-name>``, which reads as a stutter whenever the
 *  score is unnamed and repeats its type (``number-check.number-check``). Keep the part that
 *  carries meaning: the score name when it adds one, the type otherwise. */
export const evaluatorLabel = (key: string): string => {
  const separator = key.lastIndexOf('.');
  if (separator === -1) return key;
  const type = key.slice(0, separator);
  const score = key.slice(separator + 1);
  return score === type ? type : score;
};

export interface EvaluatorScore {
  key: string;
  label: string;
  value: string;
}

/** Mean per evaluator. An evaluation names its own evaluators, so these vary row to row and
 *  cannot each be a column. */
export const evaluatorScores = (evaluation: AgentEvaluationRow): EvaluatorScore[] =>
  Object.entries(evaluation.aggregate_scores ?? {}).map(([key, aggregate]) => ({
    key,
    label: evaluatorLabel(key),
    value: formatScore(aggregate?.mean),
  }));
