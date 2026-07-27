// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export {
  EvalComparisonTable,
  type EvalComparisonTableProps,
} from '@studio/components/dataViews/EvalComparisonTable/EvalComparisonTable';
export {
  ComparisonDeltaCell,
  type ComparisonDeltaCellProps,
} from '@studio/components/dataViews/EvalComparisonTable/ComparisonDeltaCell';
export {
  baselineForComparisons,
  comparisonScoresForAgentEval,
  candidatesForComparisons,
  comparisonScoresForModelEval,
  comparisonsForEvalConfig,
  deltaFromBaseline,
  metricNamesForComparisons,
  normalizeScore,
  scoreForMetric,
} from '@studio/components/dataViews/EvalComparisonTable/utils';
export type {
  EvalComparisonEntry,
  EvalComparisonScore,
  ComparisonMetricBounds,
  ComparisonMetricDelta,
} from '@studio/components/dataViews/EvalComparisonTable/types';
