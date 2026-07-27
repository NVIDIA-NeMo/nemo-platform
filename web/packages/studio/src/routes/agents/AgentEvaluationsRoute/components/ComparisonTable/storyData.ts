// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ComparisonEntry } from '@studio/routes/agents/AgentEvaluationsRoute/components/ComparisonTable/types';

export const COMPARISON_EVALUATIONS: ComparisonEntry[] = [
  {
    id: 'support-agent-v1-run',
    label: 'Baseline',
    agentName: 'support-agent-v1',
    evaluationName: 'support-agent-v1-run',
    createdAt: '2026-07-20T09:15:00Z',
    scores: [
      {
        name: 'correctness',
        count: 100,
        nan_count: 0,
        mean: 0.72,
        min: 0,
        max: 1,
        score_type: 'range',
      },
      {
        name: 'helpfulness',
        count: 100,
        nan_count: 0,
        mean: 0.68,
        min: 0,
        max: 1,
        score_type: 'range',
      },
      { name: 'safety', count: 100, nan_count: 0, mean: 0.93, min: 0, max: 1, score_type: 'range' },
    ],
  },
  {
    id: 'support-agent-v2-run',
    label: 'Candidate',
    agentName: 'support-agent-v2',
    evaluationName: 'support-agent-v2-run',
    createdAt: '2026-07-22T14:30:00Z',
    scores: [
      {
        name: 'correctness',
        count: 100,
        nan_count: 0,
        mean: 0.86,
        min: 0,
        max: 1,
        score_type: 'range',
      },
      {
        name: 'helpfulness',
        count: 100,
        nan_count: 0,
        mean: 0.82,
        min: 0,
        max: 1,
        score_type: 'range',
      },
      { name: 'safety', count: 100, nan_count: 0, mean: 0.91, min: 0, max: 1, score_type: 'range' },
    ],
  },
  {
    id: 'support-agent-v3-run',
    label: 'Safety candidate',
    agentName: 'support-agent-v3',
    evaluationName: 'support-agent-v3-run',
    createdAt: '2026-07-23T11:45:00Z',
    scores: [
      {
        name: 'correctness',
        count: 99,
        nan_count: 1,
        mean: 0.8,
        min: 0,
        max: 1,
        score_type: 'range',
      },
      {
        name: 'helpfulness',
        count: 99,
        nan_count: 1,
        mean: 0.74,
        min: 0,
        max: 1,
        score_type: 'range',
      },
      { name: 'safety', count: 99, nan_count: 1, mean: 0.98, min: 0, max: 1, score_type: 'range' },
    ],
  },
];

/** Enough runs to push the candidate columns past the viewport, so the pinned metric and
 * baseline columns can be exercised. */
export const COMPARISON_EVALUATIONS_WIDE: ComparisonEntry[] = [
  {
    id: 'sweep-baseline',
    label: 'Baseline',
    agentName: 'support-agent-v1',
    evaluationName: 'sweep-baseline',
    createdAt: '2026-07-20T09:15:00Z',
    scores: [
      {
        name: 'correctness',
        count: 100,
        nan_count: 0,
        mean: 0.72,
        min: 0,
        max: 1,
        score_type: 'range',
      },
      {
        name: 'helpfulness',
        count: 100,
        nan_count: 0,
        mean: 0.68,
        min: 0,
        max: 1,
        score_type: 'range',
      },
      { name: 'safety', count: 100, nan_count: 0, mean: 0.93, min: 0, max: 1, score_type: 'range' },
      {
        name: 'latency_s',
        count: 100,
        nan_count: 0,
        mean: 3.1,
        min: 0,
        max: 10,
        score_type: 'range',
      },
    ],
  },
  ...Array.from({ length: 8 }, (_unused, index) => ({
    id: `sweep-run-${index + 1}`,
    label: `Prompt sweep ${index + 1}`,
    agentName: `support-agent-sweep-${index + 1}`,
    evaluationName: `sweep-run-${index + 1}`,
    createdAt: '2026-07-23T11:45:00Z',
    scores: [
      {
        name: 'correctness',
        count: 100,
        nan_count: 0,
        mean: 0.62 + index * 0.04,
        min: 0,
        max: 1,
        score_type: 'range' as const,
      },
      {
        name: 'helpfulness',
        count: 100,
        nan_count: 0,
        mean: 0.8 - index * 0.03,
        min: 0,
        max: 1,
        score_type: 'range' as const,
      },
      {
        name: 'safety',
        count: 100,
        nan_count: 0,
        mean: 0.93,
        min: 0,
        max: 1,
        score_type: 'range' as const,
      },
      {
        name: 'latency_s',
        count: 100,
        nan_count: 0,
        mean: 3.1 - index * 0.2,
        min: 0,
        max: 10,
        score_type: 'range' as const,
      },
    ],
  })),
];
