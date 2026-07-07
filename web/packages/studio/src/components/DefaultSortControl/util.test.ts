// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  evaluatorField,
  evaluatorNameOf,
  formatSortString,
  isEvaluatorField,
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
});
