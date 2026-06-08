// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { datasetFileContentQueryOptions } from '@studio/api/datasets/useDatasetFileContent';

vi.mock('@nemo/sdk/generated/platform/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@nemo/sdk/generated/platform/api')>();
  return {
    ...actual,
    filesHeadFile: vi.fn().mockResolvedValue(undefined),
    filesDownloadFile: vi.fn().mockResolvedValue(new Blob(['# heading'])),
  };
});

// customFetch now handles Range requests for text files. Return a Blob that
// resolves to the expected text so the .text() call in the queryFn succeeds.
vi.mock('@nemo/sdk/generated/fetchers/platform', () => ({
  customFetch: vi.fn().mockResolvedValue(new Blob(['# heading'])),
}));

vi.mock('hyparquet', () => ({
  parquetRead: vi.fn(
    async (options: { onComplete?: (rows: Record<string, unknown>[]) => void }) => {
      options.onComplete?.([{ id: 9007199254740993n, label: 'large-int' }]);
    }
  ),
}));

describe('useDatasetFileContent gate', () => {
  const baseParams = { workspace: 'ws', name: 'ds', path: 'README.md' };

  it('allows .md files and returns content via Range fetch', async () => {
    const { queryFn } = datasetFileContentQueryOptions(baseParams);
    await expect((queryFn as () => Promise<string>)()).resolves.toBe('# heading');
  });

  it('rejects files in the binary extension blocklist', async () => {
    // .png is in BINARY_FILE_EXTENSIONS — should throw before any network call.
    const { queryFn } = datasetFileContentQueryOptions({ ...baseParams, path: 'image.png' });
    await expect((queryFn as () => Promise<string>)()).rejects.toThrow(
      /Text preview not available for binary files/
    );
  });

  it('allows files with no extension (treated as text)', async () => {
    // Files with no extension (Makefile, LICENSE, etc.) are not in the blocklist
    // and fall through to the Range fetch — treat as text.
    const { queryFn } = datasetFileContentQueryOptions({ ...baseParams, path: 'noextension' });
    await expect((queryFn as () => Promise<string>)()).resolves.toBe('# heading');
  });

  it('serializes parquet rows with BigInt columns as JSONL text', async () => {
    const { filesDownloadFile } = await import('@nemo/sdk/generated/platform/api');
    vi.mocked(filesDownloadFile).mockResolvedValueOnce(new Blob(['parquet-bytes']));

    const { queryFn } = datasetFileContentQueryOptions({
      ...baseParams,
      path: 'data/sample.parquet',
    });

    await expect((queryFn as () => Promise<string>)()).resolves.toBe(
      '{"id":"9007199254740993","label":"large-int"}\n'
    );
  });
});
