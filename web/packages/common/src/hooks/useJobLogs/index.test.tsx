// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { jobsPageJobLogs } from '@nemo/sdk/generated/platform/api';
import type { PlatformJobLog, PlatformJobLogPage } from '@nemo/sdk/generated/platform/schema';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';

import { useJobLogs } from './index';

vi.mock('@nemo/sdk/generated/platform/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@nemo/sdk/generated/platform/api')>();
  return {
    ...actual,
    jobsPageJobLogs: vi.fn(),
  };
});

const mockJobsPageJobLogs = vi.mocked(jobsPageJobLogs);

const WORKSPACE = 'test-workspace';
const JOB_NAME = 'test-job';

function makeLog(index: number): PlatformJobLog {
  return {
    timestamp: `2026-01-01T00:00:${String(index).padStart(2, '0')}Z`,
    job: JOB_NAME,
    job_step: 'step',
    job_task: 'task',
    message: `Log message ${index}`,
  };
}

function makePage(
  logs: PlatformJobLog[],
  total: number,
  nextPage: string | null = null
): PlatformJobLogPage {
  return {
    data: logs,
    total,
    next_page: nextPage ?? '',
    prev_page: '',
  };
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });

  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useJobLogs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns logs from a single page', async () => {
    const logs = [makeLog(0), makeLog(1), makeLog(2)];
    mockJobsPageJobLogs.mockResolvedValueOnce(makePage(logs, 3));

    const { result } = renderHook(() => useJobLogs({ workspace: WORKSPACE, name: JOB_NAME }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data).toEqual(logs);
    expect(result.current.total).toBe(3);
    expect(result.current.error).toBeNull();
  });

  it('paginates through multiple pages', async () => {
    const page1 = Array.from({ length: 3 }, (_, i) => makeLog(i));
    const page2 = Array.from({ length: 2 }, (_, i) => makeLog(i + 3));

    mockJobsPageJobLogs
      .mockResolvedValueOnce(makePage(page1, 5, 'cursor-1'))
      .mockResolvedValueOnce(makePage(page2, 5));

    const { result } = renderHook(
      () => useJobLogs({ workspace: WORKSPACE, name: JOB_NAME, pageSize: 3 }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data).toEqual([...page1, ...page2]);
    expect(result.current.total).toBe(5);
    expect(mockJobsPageJobLogs).toHaveBeenCalledTimes(2);
  });

  it('returns empty array when there are no logs', async () => {
    mockJobsPageJobLogs.mockResolvedValueOnce(makePage([], 0));

    const { result } = renderHook(() => useJobLogs({ workspace: WORKSPACE, name: JOB_NAME }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data).toEqual([]);
    expect(result.current.total).toBe(0);
  });

  it('is disabled when workspace or name is empty', () => {
    const { result } = renderHook(() => useJobLogs({ workspace: '', name: '' }), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.data).toEqual([]);
    expect(mockJobsPageJobLogs).not.toHaveBeenCalled();
  });

  it('respects explicit enabled: false', () => {
    const { result } = renderHook(
      () => useJobLogs({ workspace: WORKSPACE, name: JOB_NAME, enabled: false }),
      { wrapper: createWrapper() }
    );

    expect(result.current.isLoading).toBe(false);
    expect(result.current.data).toEqual([]);
    expect(mockJobsPageJobLogs).not.toHaveBeenCalled();
  });

  it('reports errors', async () => {
    mockJobsPageJobLogs.mockRejectedValueOnce(new Error('Network failure'));

    const { result } = renderHook(() => useJobLogs({ workspace: WORKSPACE, name: JOB_NAME }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.error).toBeTruthy());
  });

  it('trims logs to maxRetainedLogs keeping the tail', async () => {
    // maxPages=5, pageSize=2 -> maxRetainedLogs=10
    // 6 full pages of 2 = 12 logs total, should trim to last 10
    const pageSize = 2;
    const maxPages = 5;
    const maxRetained = maxPages * pageSize; // 10

    const pages = Array.from({ length: 6 }, (_, p) =>
      Array.from({ length: 2 }, (_, i) => makeLog(p * 2 + i))
    );

    mockJobsPageJobLogs
      .mockResolvedValueOnce(makePage(pages[0], 12, 'c1'))
      .mockResolvedValueOnce(makePage(pages[1], 12, 'c2'))
      .mockResolvedValueOnce(makePage(pages[2], 12, 'c3'))
      .mockResolvedValueOnce(makePage(pages[3], 12, 'c4'))
      .mockResolvedValueOnce(makePage(pages[4], 12, 'c5'))
      .mockResolvedValueOnce(makePage(pages[5], 12));

    const { result } = renderHook(
      () => useJobLogs({ workspace: WORKSPACE, name: JOB_NAME, pageSize, maxPages }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.data).toHaveLength(maxRetained);
    expect(result.current.data[0].message).toBe('Log message 2');
    expect(result.current.data[9].message).toBe('Log message 11');
  });

  it('caches full pages and only refetches the last page', async () => {
    const pageSize = 3;
    const fullPage = Array.from({ length: 3 }, (_, i) => makeLog(i));
    const lastPage = [makeLog(3)];
    const lastPageUpdated = [makeLog(3), makeLog(4)];

    // Initial fetch: full page + partial last page
    mockJobsPageJobLogs
      .mockResolvedValueOnce(makePage(fullPage, 4, 'c1'))
      .mockResolvedValueOnce(makePage(lastPage, 4));

    // Per-page cache entries need gcTime > 0 to survive between outer query runs
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: Infinity },
      },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(
      () => useJobLogs({ workspace: WORKSPACE, name: JOB_NAME, pageSize }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data).toHaveLength(4);
    expect(mockJobsPageJobLogs).toHaveBeenCalledTimes(2);

    // Simulate refetch: full page should come from cache, only last page refetches
    mockJobsPageJobLogs.mockClear();
    mockJobsPageJobLogs.mockResolvedValueOnce(makePage(lastPageUpdated, 5));

    const { data: refetchData } = await result.current.refetch();

    // Only 1 API call (last page). Full page resolved from cache.
    expect(mockJobsPageJobLogs).toHaveBeenCalledTimes(1);
    expect(refetchData?.logs).toHaveLength(5);
  });

  it('fetches all logs on manual refetch when disabled', async () => {
    const logs = [makeLog(0), makeLog(1)];
    mockJobsPageJobLogs.mockResolvedValueOnce(makePage(logs, 2));

    const { result } = renderHook(
      () => useJobLogs({ workspace: WORKSPACE, name: JOB_NAME, enabled: false }),
      { wrapper: createWrapper() }
    );

    expect(mockJobsPageJobLogs).not.toHaveBeenCalled();

    const { data } = await result.current.refetch();

    expect(mockJobsPageJobLogs).toHaveBeenCalledTimes(1);
    expect(data?.logs).toEqual(logs);
  });
});
