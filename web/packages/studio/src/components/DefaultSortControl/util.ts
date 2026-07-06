// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/** Always-available sort fields (no experiments needed to know them). Metrics rank on their `.mean`. */
export const STATIC_FIELDS: ReadonlyArray<{ value: string; label: string }> = [
  { value: 'cost_usd.mean', label: 'Avg Cost' },
  { value: 'latency_ms.mean', label: 'Avg Latency' },
  { value: 'run_count', label: 'Run count' },
];

/** Prefix for a per-evaluator Select option value, e.g. `evaluator:accuracy`. */
export const EVALUATOR_PREFIX = 'evaluator:';

// Evaluator names may contain dots; the `.mean` suffix is the anchor.
const EVALUATOR_FIELD = /^evaluators\.(.+)\.mean$/;

export const evaluatorField = (name: string) => `evaluators.${name}.mean`;
export const isEvaluatorField = (field: string) => EVALUATOR_FIELD.test(field);
/** Evaluator name embedded in an `evaluators.<name>.mean` field, or '' if not that shape. */
export const evaluatorNameOf = (field: string) => field.match(EVALUATOR_FIELD)?.[1] ?? '';

/**
 * The control's value is a `sort`-param string matching the API grammar: an optional leading '-'
 * (descending) followed by the metric field, e.g. `-cost_usd.mean`. Parsing/formatting keeps the
 * field and direction as separate widget state while storing/emitting the single string.
 */
export const parseSortString = (value: string): { field: string; desc: boolean } =>
  value.startsWith('-') ? { field: value.slice(1), desc: true } : { field: value, desc: false };

export const formatSortString = (field: string, desc: boolean): string => `${desc ? '-' : ''}${field}`;
