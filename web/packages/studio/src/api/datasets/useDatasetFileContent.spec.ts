// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { datasetFileContentQueryOptions } from '@studio/api/datasets/useDatasetFileContent';

vi.mock('@nemo/sdk/generated/platform/api', () => ({
  filesHeadFile: vi.fn().mockResolvedValue(undefined),
  filesDownloadFile: vi.fn().mockResolvedValue(new Blob(['# heading'])),
}));

describe('useDatasetFileContent gate', () => {
  const baseParams = { workspace: 'ws', name: 'ds', path: 'README.md' };

  it('allows .md files (preview superset)', async () => {
    const { queryFn } = datasetFileContentQueryOptions(baseParams);
    await expect((queryFn as () => Promise<string>)()).resolves.toBe('# heading');
  });

  it('rejects extensions outside PREVIEWABLE_FILE_TYPES', async () => {
    const { queryFn } = datasetFileContentQueryOptions({ ...baseParams, path: 'app.exe' });
    await expect((queryFn as () => Promise<string>)()).rejects.toThrow(/Unsupported file type/);
  });

  it('rejects files with no extension', async () => {
    const { queryFn } = datasetFileContentQueryOptions({ ...baseParams, path: 'noextension' });
    await expect((queryFn as () => Promise<string>)()).rejects.toThrow(/Unsupported file type/);
  });
});
