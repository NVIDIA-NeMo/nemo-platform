// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { PreviewRequest } from '@nemo/sdk/generated/anonymizer/schema';
import { streamAnonymizerPreview } from '@studio/routes/AnonymizerBuilderRoute/previewApi';
import { useAnonymizerPreview } from '@studio/routes/AnonymizerBuilderRoute/useAnonymizerPreview';
import { act, renderHook, waitFor } from '@testing-library/react';

vi.mock('@studio/routes/AnonymizerBuilderRoute/previewApi', () => ({
  streamAnonymizerPreview: vi.fn(),
}));

const streamMock = vi.mocked(streamAnonymizerPreview);

const requestFor = (name: string): PreviewRequest => ({ name }) as unknown as PreviewRequest;

const deferred = <T>(): { promise: Promise<T>; resolve: (value: T) => void } => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
};

const renderPreview = (getRequest: () => Promise<PreviewRequest | undefined>) =>
  renderHook(() => useAnonymizerPreview({ workspace: 'default', accessToken: 't', getRequest }));

beforeEach(() => {
  streamMock.mockReset();
});

describe('useAnonymizerPreview', () => {
  it('ignores a run whose request resolves after a newer one started', async () => {
    const first = deferred<PreviewRequest | undefined>();
    const second = deferred<PreviewRequest | undefined>();
    const pending = [first.promise, second.promise];
    const getRequest = vi.fn(() => pending.shift() ?? Promise.resolve(undefined));

    streamMock.mockImplementation(async (_workspace, request, _token, _signal, onFrame) => {
      onFrame({
        kind: 'trace_dataset',
        records: [{ from: (request as unknown as { name: string }).name }],
        original_text_column: 'text',
      });
    });

    const { result } = renderPreview(getRequest);

    act(() => {
      void result.current.runPreview();
      void result.current.runPreview();
    });

    await act(async () => {
      second.resolve(requestFor('second'));
      first.resolve(requestFor('first'));
      await Promise.resolve();
    });

    await waitFor(() => expect(streamMock).toHaveBeenCalledTimes(1));
    expect(result.current.result.records).toEqual([{ from: 'second' }]);
  });

  it('surfaces an error when building the request throws', async () => {
    const getRequest = vi.fn(() => Promise.reject(new Error('Could not validate the form.')));

    const { result } = renderPreview(getRequest);

    await act(async () => {
      await result.current.runPreview();
    });

    expect(result.current.error).toBe('Could not validate the form.');
    expect(streamMock).not.toHaveBeenCalled();
  });

  it('stays idle when the form has no request to preview', async () => {
    const getRequest = vi.fn(() => Promise.resolve(undefined));

    const { result } = renderPreview(getRequest);

    await act(async () => {
      await result.current.runPreview();
    });

    expect(result.current.hasRun).toBe(false);
    expect(result.current.isPreviewing).toBe(false);
    expect(streamMock).not.toHaveBeenCalled();
  });
});
