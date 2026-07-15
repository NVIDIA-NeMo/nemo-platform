// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  evaluatorField,
  evaluatorNameOf,
  formatSortList,
  formatSortString,
  isEvaluatorField,
  parseSortList,
  parseSortString,
} from '@studio/components/DefaultSortControl/util';

describe('DefaultSortControl util', () => {
  it('builds and parses evaluator field paths', () => {
    expect(evaluatorField('accuracy')).toBe('evaluators.accuracy.mean');
    expect(evaluatorNameOf('evaluators.accuracy.mean')).toBe('accuracy');
    // Evaluator names may contain dots; the .mean suffix is the anchor.
    expect(evaluatorNameOf('evaluators.harbor.verifier.mean')).toBe('harbor.verifier');
    expect(evaluatorNameOf('cost_usd.mean')).toBe('');
    expect(isEvaluatorField('evaluators.accuracy.mean')).toBe(true);
    expect(isEvaluatorField('cost_usd.mean')).toBe(false);
  });

  it('round-trips sort strings through parse/format', () => {
    expect(parseSortString('-cost_usd.mean')).toEqual({ field: 'cost_usd.mean', desc: true });
    expect(parseSortString('run_count')).toEqual({ field: 'run_count', desc: false });
    expect(formatSortString('cost_usd.mean', true)).toBe('-cost_usd.mean');
    expect(formatSortString('run_count', false)).toBe('run_count');
  });

  it('round-trips multi-field sort lists, preserving order', () => {
    expect(parseSortList('-evaluators.reward.mean,cost_usd.mean')).toEqual([
      { field: 'evaluators.reward.mean', desc: true },
      { field: 'cost_usd.mean', desc: false },
    ]);
    expect(
      formatSortList([
        { field: 'evaluators.reward.mean', desc: true },
        { field: 'cost_usd.mean', desc: false },
      ])
    ).toBe('-evaluators.reward.mean,cost_usd.mean');
  });

  it('parses a single-field list and ignores blank/whitespace tokens', () => {
    expect(parseSortList('-cost_usd.mean')).toEqual([{ field: 'cost_usd.mean', desc: true }]);
    expect(parseSortList(' -cost_usd.mean , latency_ms.mean ')).toEqual([
      { field: 'cost_usd.mean', desc: true },
      { field: 'latency_ms.mean', desc: false },
    ]);
    expect(parseSortList('')).toEqual([]);
    expect(parseSortList('cost_usd.mean,,')).toEqual([{ field: 'cost_usd.mean', desc: false }]);
  });
});
