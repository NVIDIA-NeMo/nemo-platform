// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getEvaluationsWithMetricsQueryOptions } from '@studio/api/evaluation/useEvaluationsWithMetrics';

describe('getEvaluationsWithMetricsQueryOptions', () => {
  it('returns query options with correct key', () => {
    const opts = getEvaluationsWithMetricsQueryOptions('ws1');
    expect(opts.queryKey).toEqual(['evaluationsWithMetrics', undefined]);
    expect(typeof opts.queryFn).toBe('function');
  });

  it('includes query params in query key', () => {
    const query = { page: 2, page_size: 10 };
    const opts = getEvaluationsWithMetricsQueryOptions('ws1', query);
    expect(opts.queryKey).toEqual(['evaluationsWithMetrics', query]);
  });
});
