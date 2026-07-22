// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { DataDesignerConfig } from '@nemo/sdk/generated/data-designer/schema';
import { usePreview } from '@studio/components/NewDataDesignerJobForm/usePreview';
import { act, renderHook, waitFor } from '@testing-library/react';

const streamPreviewMock = vi.fn();
vi.mock('@studio/components/NewDataDesignerJobForm/previewApi', async () => {
  const actual = await vi.importActual<
    typeof import('@studio/components/NewDataDesignerJobForm/previewApi')
  >('@studio/components/NewDataDesignerJobForm/previewApi');
  return { ...actual, streamPreview: (...a: unknown[]) => streamPreviewMock(...a) };
});

const CONFIG = { columns: [] } as unknown as DataDesignerConfig;

describe('usePreview', () => {
  beforeEach(() => streamPreviewMock.mockReset());

  it('surfaces an error when building the config throws (e.g. invalid JSON field)', async () => {
    const { result } = renderHook(() =>
      usePreview({
        workspace: 'ws',
        accessToken: 'token',
        getCurrentConfig: () => {
          throw new SyntaxError('Unexpected token n in JSON at position 2');
        },
      })
    );

    await act(async () => {
      await result.current.runPreview();
    });

    // A thrown config-build error must be shown to the user, not silently swallowed.
    await waitFor(() => {
      expect(result.current.previewLogs).not.toBe('');
    });
    expect(result.current.previewLogs).toMatch(/JSON|error|preview/i);
    expect(result.current.isPreviewing).toBe(false);
    expect(streamPreviewMock).not.toHaveBeenCalled();
  });

  it('streams normally when the config builds', async () => {
    streamPreviewMock.mockImplementation(async (...args: unknown[]) => {
      const onLine = args.find((a) => typeof a === 'function') as ((l: string) => void) | undefined;
      onLine?.('a log line');
    });
    const { result } = renderHook(() =>
      usePreview({ workspace: 'ws', accessToken: 'token', getCurrentConfig: () => CONFIG })
    );

    await act(async () => {
      await result.current.runPreview();
    });

    expect(streamPreviewMock).toHaveBeenCalled();
    expect(result.current.previewLogs).toContain('a log line');
    expect(result.current.isPreviewing).toBe(false);
  });
});
