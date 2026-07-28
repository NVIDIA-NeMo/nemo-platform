// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RunJob } from '@nemo/sdk/generated/anonymizer/schema';
import {
  jobSource,
  jobStrategy,
  orderResultColumns,
  parseArtifactUrl,
  parseJsonLines,
} from '@studio/routes/AnonymizerJobDetailRoute/util';

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

describe('parseArtifactUrl', () => {
  it('splits the fileset reference from the path', () => {
    expect(parseArtifactUrl('default/job-fileset-deer#results/attempt-1/artifacts')).toEqual({
      fileset: 'job-fileset-deer',
      basePath: 'results/attempt-1/artifacts',
    });
  });

  it('is undefined without both halves', () => {
    expect(parseArtifactUrl(undefined)).toBeUndefined();
    expect(parseArtifactUrl('default/job-fileset-deer')).toBeUndefined();
    expect(parseArtifactUrl('#results/artifacts')).toBeUndefined();
  });
});

describe('parseJsonLines', () => {
  it('reads one object per line and skips unparseable ones', () => {
    expect(parseJsonLines<{ a: number }>('{"a":1}\n{"a":2}\n')).toEqual([{ a: 1 }, { a: 2 }]);
    expect(parseJsonLines('{"a":1}\nnot json\n')).toEqual([{ a: 1 }]);
    expect(parseJsonLines(undefined)).toEqual([]);
  });
});

describe('orderResultColumns', () => {
  it('puts the rewrite output next to its source column', () => {
    expect(
      orderResultColumns(['biography', 'biography_rewritten', 'utility_score'], 'biography')
    ).toEqual(['biography', 'biography_rewritten', 'utility_score']);
  });

  it('prefers the replaced column over other same-prefix columns', () => {
    expect(
      orderResultColumns(
        ['biography', 'biography_with_spans', 'final_entities', 'biography_replaced'],
        'biography'
      )
    ).toEqual(['biography', 'biography_replaced', 'biography_with_spans', 'final_entities']);
  });

  it('leaves the order alone when the text column is unknown or absent', () => {
    expect(orderResultColumns(['a', 'b'], undefined)).toEqual(['a', 'b']);
    expect(orderResultColumns(['a', 'b'], 'missing')).toEqual(['a', 'b']);
  });
});
