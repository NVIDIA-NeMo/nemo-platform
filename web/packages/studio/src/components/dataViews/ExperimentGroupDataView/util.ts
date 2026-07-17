// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/** Evaluator names in the rows, unioned with any that have an active filter so a column (and its
 * filter-panel entry / applied-filter chip) survives a zero-result filter. Sorted for stable order. */
export const deriveEvaluatorNames = (
  rows: readonly { aggregate_scores?: Record<string, unknown> }[],
  columnFilters: readonly { id: string }[]
): string[] => {
  const fromData = rows.flatMap((row) => Object.keys(row.aggregate_scores ?? {}));
  const fromFilters = columnFilters
    .map((filter) => filter.id.match(/^evaluator-(.+)$/)?.[1])
    .filter((name): name is string => name != null);
  return [...new Set([...fromData, ...fromFilters])].sort();
};

/**
 * Formats an evaluator's mean score for display. Scores in the normalized 0–1 range read best as
 * percentages; values outside that range are on a different scale (e.g. a 1–5 or 1–10 rubric), so
 * they're shown as a raw number rather than a misleading percentage. Missing/invalid means render
 * `emptyValue` — callers pass the placeholder their surface uses (e.g. `-` vs `—`).
 */
export const formatEvaluatorScore = (mean: number | null | undefined, emptyValue = '—'): string => {
  if (mean == null || !Number.isFinite(mean)) return emptyValue;
  return mean >= 0 && mean <= 1 ? `${(mean * 100).toFixed(1)}%` : mean.toFixed(3);
};
