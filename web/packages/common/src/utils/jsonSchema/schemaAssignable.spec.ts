// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { isSchemaAssignableFile } from '@nemo/common/src/utils/jsonSchema/schemaAssignable';

describe('isSchemaAssignableFile', () => {
  it.each([
    'data.json',
    'rows.jsonl',
    'subdir/sample.json',
    'deep/nested/path/file.jsonl',
    'rows.csv',
    'subdir/data.csv',
    'train.parquet',
    'subdir/data.parquet',
  ])('%s -> true', (path) => {
    expect(isSchemaAssignableFile(path)).toBe(true);
  });

  it('matches uppercase extensions case-insensitively', () => {
    expect(isSchemaAssignableFile('DATA.JSON')).toBe(true);
    expect(isSchemaAssignableFile('rows.JsonL')).toBe(true);
    expect(isSchemaAssignableFile('data.CSV')).toBe(true);
    expect(isSchemaAssignableFile('train.PARQUET')).toBe(true);
  });

  it.each(['README.md', 'LICENSE', 'image.png', 'config.yaml', 'archive.tar.gz', 'noext'])(
    '%s -> false',
    (path) => {
      expect(isSchemaAssignableFile(path)).toBe(false);
    }
  );

  it('rejects an empty string', () => {
    expect(isSchemaAssignableFile('')).toBe(false);
  });
});
