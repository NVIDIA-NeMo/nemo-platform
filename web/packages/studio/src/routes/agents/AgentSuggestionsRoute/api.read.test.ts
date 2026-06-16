// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  isCanceledError,
  loadSnapshot,
  loadSuggestionsFromFileset,
} from '@studio/routes/agents/AgentSuggestionsRoute/api';
import type { Mock } from 'vitest';

const filesDownloadFileMock = vi.fn();

vi.mock('@nemo/sdk/generated/fetchers/platform', () => ({
  customFetch: vi.fn(),
}));

vi.mock('@nemo/sdk/generated/platform/api', () => ({
  filesCreateFileset: vi.fn(),
  filesDownloadFile: (...args: unknown[]) => filesDownloadFileMock(...args),
  filesListFilesetFiles: vi.fn(),
  filesUploadFile: vi.fn(),
  modelsListModels: vi.fn(),
}));

beforeEach(() => {
  filesDownloadFileMock.mockReset();
});

const mock404 = (fn: Mock) => fn.mockRejectedValueOnce({ response: { status: 404 } });

const mock500 = (fn: Mock) => fn.mockRejectedValueOnce({ response: { status: 500 } });

const mockBlob = (text: string): Blob => ({ text: () => Promise.resolve(text) }) as unknown as Blob;

describe('loadSuggestionsFromFileset', () => {
  it('returns [] when the file is missing (404)', async () => {
    mock404(filesDownloadFileMock);
    await expect(loadSuggestionsFromFileset('ws-a')).resolves.toEqual([]);
  });

  it('rethrows on 5xx so a transient failure is not mistaken for empty history', async () => {
    mock500(filesDownloadFileMock);
    // The check that matters: the call must throw, not silently resolve to [].
    // If it resolved to [], a subsequent run() merge would erase applied state.
    await expect(loadSuggestionsFromFileset('ws-a')).rejects.toMatchObject({
      response: { status: 500 },
    });
  });

  it('parses the JSONL on success', async () => {
    filesDownloadFileMock.mockResolvedValueOnce(
      mockBlob('{"type":"guardrails","title":"a","detail":"b"}\n')
    );
    const result = await loadSuggestionsFromFileset('ws-a');
    expect(result).toEqual([{ type: 'guardrails', title: 'a', detail: 'b' }]);
  });
});

describe('loadSnapshot', () => {
  it('returns null when the snapshot is missing (404)', async () => {
    mock404(filesDownloadFileMock);
    await expect(loadSnapshot('ws-a')).resolves.toBeNull();
  });

  it('rethrows on 5xx so a transient failure is not mistaken for first-run', async () => {
    mock500(filesDownloadFileMock);
    // If 5xx returned null, every existing model would re-emit as
    // `new_model_scan` on the next run.
    await expect(loadSnapshot('ws-a')).rejects.toMatchObject({
      response: { status: 500 },
    });
  });
});

describe('isCanceledError', () => {
  it('matches cancellation-shaped errors only', () => {
    const canceled = [{ name: 'CanceledError' }, { code: 'ERR_CANCELED' }, { name: 'AbortError' }];
    const unrelated = [new Error('boom'), { response: { status: 500 } }, undefined, null];

    for (const error of canceled) {
      expect(isCanceledError(error)).toBe(true);
    }
    for (const error of unrelated) {
      expect(isCanceledError(error)).toBe(false);
    }
  });
});
