// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RunJob } from '@nemo/sdk/generated/anonymizer/schema';
import { jobSource, jobStrategy } from '@studio/routes/AnonymizerJobDetailRoute/util';

const job = (config: unknown, source?: string): RunJob =>
  ({ name: 'job-1', spec: { request: { config, data: { source } } } }) as RunJob;

describe('jobStrategy', () => {
  it('reads the replace kind', () => {
    expect(jobStrategy(job({ replace: { kind: 'hash' } }))).toBe('hash');
  });

  it('reports rewrite jobs', () => {
    expect(jobStrategy(job({ rewrite: { risk_tolerance: 'low' } }))).toBe('rewrite');
  });

  it('is undefined when the spec carries no config', () => {
    expect(jobStrategy({ name: 'job-1' } as RunJob)).toBeUndefined();
    expect(jobStrategy(job({}))).toBeUndefined();
  });
});

describe('jobSource', () => {
  it('reads the data source, and tolerates a missing spec', () => {
    expect(jobSource(job({ replace: { kind: 'hash' } }, 's3://x.csv'))).toBe('s3://x.csv');
    expect(jobSource({ name: 'job-1' } as RunJob)).toBeUndefined();
  });
});
