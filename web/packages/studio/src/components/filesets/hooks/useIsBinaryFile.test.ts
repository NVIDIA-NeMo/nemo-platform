// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useIsBinaryFile } from '@studio/components/filesets/hooks/useIsBinaryFile';
import { useQuery, UseQueryResult } from '@tanstack/react-query';
import { renderHook } from '@testing-library/react';

vi.mock('@tanstack/react-query');
vi.mock('@nemo/sdk/generated/fetchers/platform');
vi.mock('@nemo/sdk/generated/platform/api', () => ({
  getFilesDownloadFileQueryKey: vi.fn(() => ['/files/download']),
}));
vi.mock('axios', () => {
  const mockInstance = {
    head: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  };
  return { default: mockInstance };
});

const mockUseQuery = vi.mocked(useQuery);

describe('useIsBinaryFile', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseQuery.mockReturnValue({
      data: false,
      isPending: false,
      refetch: vi.fn(),
      isFetching: false,
      isStale: false,
      isError: false,
      error: null,
      failureCount: 0,
      failureReason: null,
      isFetchNextPageEnabled: undefined,
      dataUpdateCount: 0,
      dataUpdatedAt: 0,
      errorUpdateCount: 0,
      errorUpdatedAt: 0,
      fetchStatus: 'idle',
      status: 'success',
      variables: undefined,
      queryKey: [],
      queryHash: '',
      queryFn: undefined,
      queryKeyHashFn: undefined,
      meta: undefined,
      isLoading: false,
      isLoadingError: false,
      isRefetchError: false,
      isSuccess: true,
      isObservingMisorderedIndex: false,
    } as unknown as UseQueryResult<boolean, Error>);
  });

  it('returns isBinary=false for .jsonl files without a HEAD request', () => {
    const { result } = renderHook(() =>
      useIsBinaryFile('default', 'test-dataset', 'data/test.jsonl')
    );

    expect(result.current).toEqual({ isBinary: false, isLoading: false });
    // Query should be disabled for known text extensions
    expect(mockUseQuery).toHaveBeenCalledWith(expect.objectContaining({ enabled: false }));
  });

  it('returns isBinary=false for .json files without a HEAD request', () => {
    const { result } = renderHook(() => useIsBinaryFile('default', 'test-dataset', 'config.json'));

    expect(result.current).toEqual({ isBinary: false, isLoading: false });
  });

  it('returns isBinary=false for .csv files without a HEAD request', () => {
    const { result } = renderHook(() => useIsBinaryFile('default', 'test-dataset', 'data.csv'));

    expect(result.current).toEqual({ isBinary: false, isLoading: false });
  });

  it('returns isBinary=false for .py files without a HEAD request', () => {
    const { result } = renderHook(() => useIsBinaryFile('default', 'test-dataset', 'script.py'));

    expect(result.current).toEqual({ isBinary: false, isLoading: false });
  });

  it('returns isBinary=false for .yaml and .yml files', () => {
    const { result } = renderHook(() => useIsBinaryFile('default', 'test-dataset', 'config.yaml'));

    expect(result.current).toEqual({ isBinary: false, isLoading: false });
  });

  it('returns isBinary=false for .md files', () => {
    const { result } = renderHook(() => useIsBinaryFile('default', 'test-dataset', 'README.md'));

    expect(result.current).toEqual({ isBinary: false, isLoading: false });
  });

  it('returns isBinary=false when filePath is undefined', () => {
    const { result } = renderHook(() => useIsBinaryFile('default', 'test-dataset', undefined));

    expect(result.current).toEqual({ isBinary: false, isLoading: false });
  });

  it('returns isBinary=true for .png files (binary blocklist)', () => {
    const { result } = renderHook(() => useIsBinaryFile('default', 'test-dataset', 'image.png'));

    expect(result.current).toEqual({ isBinary: true, isLoading: false });
  });

  it('returns isBinary=true for .zip files (binary blocklist)', () => {
    const { result } = renderHook(() => useIsBinaryFile('default', 'test-dataset', 'archive.zip'));

    expect(result.current).toEqual({ isBinary: true, isLoading: false });
  });

  it('enables the HEAD query for unknown extensions', () => {
    renderHook(() => useIsBinaryFile('default', 'test-dataset', 'data.unknown'));

    expect(mockUseQuery).toHaveBeenCalledWith(expect.objectContaining({ enabled: true }));
  });
});
