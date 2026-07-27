// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export {
  ComparisonTable,
  type ComparisonTableProps,
} from '@studio/routes/agents/AgentEvaluationsRoute/components/ComparisonTable/ComparisonTable';
export {
  ComparisonDeltaCell,
  type ComparisonDeltaCellProps,
} from '@studio/routes/agents/AgentEvaluationsRoute/components/ComparisonTable/ComparisonDeltaCell';
export {
  baselineForComparisons,
  candidatesForComparisons,
  comparisonsForEvalConfig,
  deltaFromBaseline,
  metricNamesForComparisons,
  normalizeScore,
  scoreForMetric,
  type ComparisonEntry,
  type ComparisonMetricBounds,
  type ComparisonMetricDelta,
} from '@studio/routes/agents/AgentEvaluationsRoute/components/ComparisonTable/types';
