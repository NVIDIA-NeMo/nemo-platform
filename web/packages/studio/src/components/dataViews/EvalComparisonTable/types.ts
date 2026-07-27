// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/** The aggregate score fields common to agent and model evaluation results. */
export interface EvalComparisonScore {
  readonly name: string;
  readonly mean: number | null;
}

/** A completed evaluation run, represented in the common shape consumed by comparison views.
 * All entries passed to a comparison component must use the same persisted eval config. */
export interface EvalComparisonEntry {
  readonly id: string;
  readonly label: string;
  readonly createdAt: string | null;
  readonly scores: readonly EvalComparisonScore[];
}

/** The expected range for a score. Supplying bounds keeps radar axes meaningful for scores
 * whose scale is not the usual 0–1 range. */
export interface ComparisonMetricBounds {
  readonly min: number;
  readonly max: number;
}

/** One metric's value in a non-baseline run, alongside the baseline it is measured against. */
export interface ComparisonMetricDelta {
  readonly value: number | null;
  readonly baselineValue: number | null;
  /** `value - baselineValue`, or null when either side has no score. */
  readonly difference: number | null;
}
