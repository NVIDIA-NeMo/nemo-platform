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
