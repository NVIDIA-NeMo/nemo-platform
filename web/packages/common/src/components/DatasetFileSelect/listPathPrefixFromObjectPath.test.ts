// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { listPathPrefixFromObjectPath } from '@nemo/common/src/components/DatasetFileSelect/parseFilesetLocation';

describe('listPathPrefixFromObjectPath', () => {
  it('returns undefined for an empty path', () => {
    expect(listPathPrefixFromObjectPath('')).toBeUndefined();
  });

  it('strips trailing slashes and treats a single segment without a dot as a directory prefix', () => {
    expect(listPathPrefixFromObjectPath('outputs')).toBe('outputs');
    expect(listPathPrefixFromObjectPath('outputs///')).toBe('outputs');
  });

  it('returns undefined for a single-segment path that looks like a file (contains a dot)', () => {
    expect(listPathPrefixFromObjectPath('train.jsonl')).toBeUndefined();
    expect(listPathPrefixFromObjectPath('archive.tar.gz')).toBeUndefined();
  });

  it('returns the parent directory for a nested path whose last segment looks like a file', () => {
    expect(listPathPrefixFromObjectPath('data/part.parquet')).toBe('data');
    expect(listPathPrefixFromObjectPath('run/output.csv')).toBe('run');
  });

  it('returns the full path when no segment looks like a file (directory-style key)', () => {
    expect(listPathPrefixFromObjectPath('results/att/artifacts')).toBe('results/att/artifacts');
  });

  it('treats hidden files like .gitignore as files: parent prefix, or undefined at fileset root', () => {
    expect(listPathPrefixFromObjectPath('repo/.gitignore')).toBe('repo');
    expect(listPathPrefixFromObjectPath('.gitignore')).toBeUndefined();
    expect(listPathPrefixFromObjectPath('.env.local')).toBeUndefined();
  });

  it('treats dot-prefixed last segments as files (limitation: dot-directories become parent-only)', () => {
    expect(listPathPrefixFromObjectPath('src/.config')).toBe('src');
  });
});
