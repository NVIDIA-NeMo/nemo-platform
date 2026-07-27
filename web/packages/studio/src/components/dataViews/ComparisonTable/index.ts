// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export {
  ComparisonTable,
  type ComparisonTableProps,
} from '@studio/components/dataViews/ComparisonTable/ComparisonTable';
export {
  ComparisonDeltaCell,
  type ComparisonDeltaCellProps,
} from '@studio/components/dataViews/ComparisonTable/ComparisonDeltaCell';
export {
  baselineForComparisons,
  candidatesForComparisons,
  comparisonsForEvalConfig,
  deltaFromBaseline,
  metricNamesForComparisons,
  normalizeScore,
  scoreForMetric,
} from '@studio/components/dataViews/ComparisonTable/comparisonScores';
export type {
  ComparisonEntry,
  ComparisonMetricBounds,
  ComparisonMetricDelta,
} from '@studio/components/dataViews/ComparisonTable/types';
