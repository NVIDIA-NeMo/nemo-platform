// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/** Sort fields available without inspecting experiments: entity columns + metrics (metrics rank on
 * their `.mean`). Evaluator fields are discovered per group and appended by the control. */
export const STATIC_FIELDS: ReadonlyArray<{ value: string; label: string }> = [
  { value: 'name', label: 'Name' },
  { value: 'created_at', label: 'Created' },
  { value: 'cost_usd.mean', label: 'Avg Cost' },
  { value: 'latency_ms.mean', label: 'Avg Latency' },
  { value: 'run_count', label: 'Run Count' },
];

/** Prefix for a per-evaluator Select option value, e.g. `evaluator:accuracy`. */
export const EVALUATOR_PREFIX = 'evaluator:';

/** Default when a group hasn't set one — newest first. Mirrors the backend entity default. */
export const DEFAULT_SORT = '-created_at';

// Evaluator names may contain dots; the `.mean` suffix is the anchor.
const EVALUATOR_FIELD = /^evaluators\.(.+)\.mean$/;

export const evaluatorField = (name: string): string => `evaluators.${name}.mean`;
export const isEvaluatorField = (field: string): boolean => EVALUATOR_FIELD.test(field);
/** Evaluator name embedded in an `evaluators.<name>.mean` field, or '' if not that shape. */
export const evaluatorNameOf = (field: string): string => field.match(EVALUATOR_FIELD)?.[1] ?? '';

/**
 * The control's value is a `sort`-param string matching the API grammar: an optional leading '-'
 * (descending) followed by the metric field, e.g. `-cost_usd.mean`. Parsing/formatting keeps the
 * field and direction as separate widget state while storing/emitting the single string.
 */
export const parseSortString = (value: string): { field: string; desc: boolean } =>
  value.startsWith('-') ? { field: value.slice(1), desc: true } : { field: value, desc: false };

export const formatSortString = (field: string, desc: boolean): string =>
  `${desc ? '-' : ''}${field}`;
