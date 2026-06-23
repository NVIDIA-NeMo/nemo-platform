// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ExperimentResponse } from '@nemo/sdk/generated/platform/schema';
import { toCostLatencyPoints } from '@nemo/studio-plugins-example/experiment-insights/costLatency';

type Source = Pick<ExperimentResponse, 'name' | 'cost_usd' | 'latency_ms'>;

const experiment = (name: string, cost?: number, latency?: number): Source => ({
  name,
  cost_usd: cost === undefined ? undefined : { mean: cost },
  latency_ms: latency === undefined ? undefined : { mean: latency },
});

describe('toCostLatencyPoints', () => {
  it('keeps only experiments reporting both a mean cost and a mean latency', () => {
    const points = toCostLatencyPoints([
      experiment('a', 0.01, 120),
      experiment('b', 0.02, undefined), // missing latency
      experiment('c', undefined, 80), // missing cost
      experiment('d', undefined, undefined), // missing both
    ]);

    expect(points).toEqual([{ name: 'a', cost: 0.01, latency: 120 }]);
  });

  it('maps every fully-populated experiment to a point, preserving order', () => {
    const points = toCostLatencyPoints([experiment('a', 0.01, 120), experiment('b', 0.05, 300)]);

    expect(points.map((p) => p.name)).toEqual(['a', 'b']);
    expect(points[1]).toEqual({ name: 'b', cost: 0.05, latency: 300 });
  });

  it('returns an empty array when no experiments are in view', () => {
    expect(toCostLatencyPoints([])).toEqual([]);
  });
});
