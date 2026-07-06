// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { deriveEvaluatorNames } from '@studio/components/dataViews/ExperimentGroupDataView/util';

describe('deriveEvaluatorNames', () => {
  it('returns the sorted, de-duplicated union of evaluator names across rows', () => {
    const rows = [
      { aggregate_scores: { helpfulness: { mean: 0.8 }, accuracy: { mean: 0.9 } } },
      { aggregate_scores: { accuracy: { mean: 0.5 } } },
      {}, // a row with no scores
    ];

    expect(deriveEvaluatorNames(rows, [])).toEqual(['accuracy', 'helpfulness']);
  });

  // Regression: a zero-result evaluator filter empties the rows, which would otherwise drop the
  // dynamic column and hide its filter chip/panel entry while the filter persists in state and URL.
  it('keeps an evaluator with an active filter even when no rows match', () => {
    expect(deriveEvaluatorNames([], [{ id: 'evaluator-accuracy' }])).toEqual(['accuracy']);
  });

  it('unions data-derived names with active-filter names', () => {
    const rows = [{ aggregate_scores: { accuracy: { mean: 0.9 } } }];

    expect(deriveEvaluatorNames(rows, [{ id: 'evaluator-helpfulness' }])).toEqual([
      'accuracy',
      'helpfulness',
    ]);
  });

  it('ignores non-evaluator filters (cost, latency, text columns)', () => {
    const filters = [
      { id: 'cost_usd' },
      { id: 'latency_ms' },
      { id: 'dataset_name' },
      { id: 'evaluator-accuracy' },
    ];

    expect(deriveEvaluatorNames([], filters)).toEqual(['accuracy']);
  });

  it('handles evaluator names containing hyphens', () => {
    expect(deriveEvaluatorNames([], [{ id: 'evaluator-tool-use-quality' }])).toEqual([
      'tool-use-quality',
    ]);
  });
});
