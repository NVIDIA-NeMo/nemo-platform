// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { fetchAllPages, type PaginatedResponse } from '@nemo/common/src/api/fetchAllPages';

const page = (data: number[], totalPages?: number): PaginatedResponse<number> => ({
  data,
  pagination: totalPages === undefined ? undefined : { total_pages: totalPages },
});

describe('fetchAllPages', () => {
  it('concatenates every page up to total_pages', async () => {
    const fetchPage = vi
      .fn<(p: number, size: number) => Promise<PaginatedResponse<number>>>()
      .mockResolvedValueOnce(page([1, 2], 3))
      .mockResolvedValueOnce(page([3, 4], 3))
      .mockResolvedValueOnce(page([5], 3));

    await expect(fetchAllPages(fetchPage, { pageSize: 2 })).resolves.toEqual([1, 2, 3, 4, 5]);
    expect(fetchPage.mock.calls).toEqual([
      [1, 2],
      [2, 2],
      [3, 2],
    ]);
  });

  it('stops on a short page when the response omits total_pages', async () => {
    const fetchPage = vi
      .fn<(p: number, size: number) => Promise<PaginatedResponse<number>>>()
      .mockResolvedValueOnce(page([1, 2]))
      .mockResolvedValueOnce(page([3]));

    await expect(fetchAllPages(fetchPage, { pageSize: 2 })).resolves.toEqual([1, 2, 3]);
    expect(fetchPage).toHaveBeenCalledTimes(2);
  });

  it('treats a missing data array as an empty page', async () => {
    const fetchPage = vi.fn().mockResolvedValue({});

    await expect(fetchAllPages(fetchPage)).resolves.toEqual([]);
    expect(fetchPage).toHaveBeenCalledTimes(1);
  });

  it('truncates at maxPages rather than looping forever', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const fetchPage = vi.fn().mockResolvedValue(page([1, 2]));

    await expect(fetchAllPages(fetchPage, { pageSize: 2, maxPages: 3 })).resolves.toEqual([
      1, 2, 1, 2, 1, 2,
    ]);
    expect(fetchPage).toHaveBeenCalledTimes(3);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('truncated'));
    warn.mockRestore();
  });
});
