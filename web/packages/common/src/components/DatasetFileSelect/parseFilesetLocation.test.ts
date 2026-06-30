// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  parseFilesetLocation,
  type ParsedFilesetArtifactUrl,
} from '@nemo/common/src/components/DatasetFileSelect/parseFilesetLocation';

type Case = readonly [
  url: string,
  workspaceFallback: string | undefined,
  expected: ParsedFilesetArtifactUrl | null,
];

/** Same shapes as Python `parse_fileset_ref`: fileset://, hash, legacy slashes, fallback workspace. */
const CASES: Case[] = [
  ['fileset://ws-1/my-ds/', undefined, { workspace: 'ws-1', name: 'my-ds', objectPath: '' }],
  ['fileset://ws-1/my-ds', undefined, { workspace: 'ws-1', name: 'my-ds', objectPath: '' }],
  [
    'ws-1/my-ds#results/att/artifacts',
    undefined,
    {
      workspace: 'ws-1',
      name: 'my-ds',
      objectPath: 'results/att/artifacts',
      filesListPathPrefix: 'results/att/artifacts',
    },
  ],
  [
    'my-ds#train.jsonl',
    'default-ws',
    { workspace: 'default-ws', name: 'my-ds', objectPath: 'train.jsonl' },
  ],
  [
    'fileset://ws/fs#out/part.parquet',
    undefined,
    {
      workspace: 'ws',
      name: 'fs',
      objectPath: 'out/part.parquet',
      filesListPathPrefix: 'out',
    },
  ],
  [
    'ws/my-fs/results/abc/artifacts',
    undefined,
    {
      workspace: 'ws',
      name: 'my-fs',
      objectPath: 'results/abc/artifacts',
      filesListPathPrefix: 'results/abc/artifacts',
    },
  ],
  [
    'fileset://ws-1/my-ds/part/data.parquet',
    undefined,
    {
      workspace: 'ws-1',
      name: 'my-ds',
      objectPath: 'part/data.parquet',
      filesListPathPrefix: 'part',
    },
  ],
  [
    'fileset://ws/fs/data.parquet',
    undefined,
    { workspace: 'ws', name: 'fs', objectPath: 'data.parquet' },
  ],
  ['my-ds#only', undefined, null],
];

describe('parseFilesetLocation', () => {
  it.each(CASES)('%s', (url, workspaceFallback, expected) => {
    expect(parseFilesetLocation(url, workspaceFallback)).toEqual(expected);
  });

  it('returns null for blank input', () => {
    expect(parseFilesetLocation('')).toBeNull();
    expect(parseFilesetLocation('   ')).toBeNull();
  });
});
