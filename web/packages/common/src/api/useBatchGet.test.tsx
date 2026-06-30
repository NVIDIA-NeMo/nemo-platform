// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { ReactNode } from 'react';
import type { MockedFunction } from 'vitest';

import { useBatchGet } from './useBatchGet';

interface TestItem {
  id: string;
  name: string;
  value: number;
}

// Test wrapper component
const createWrapper = () => {
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
};

describe('useBatchGet', () => {
  let mockFetchFn: MockedFunction<(urn: string) => Promise<TestItem>>;

  beforeEach(() => {
    mockFetchFn = vi.fn();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Basic Functionality', () => {
    it('should fetch all items when urns are provided', async () => {
      const mockData: TestItem[] = [
        { id: 'urn1', name: 'Item 1', value: 100 },
        { id: 'urn2', name: 'Item 2', value: 200 },
        { id: 'urn3', name: 'Item 3', value: 300 },
      ];

      mockFetchFn
        .mockResolvedValueOnce(mockData[0])
        .mockResolvedValueOnce(mockData[1])
        .mockResolvedValueOnce(mockData[2]);

      const { result } = renderHook(
        () =>
          useBatchGet({
            urns: ['urn1', 'urn2', 'urn3'],
            fetchFn: mockFetchFn,
            queryKeyPrefix: 'test-items',
          }),
        {
          wrapper: createWrapper(),
        }
      );

      expect(result.current.isLoading).toBe(true);
      expect(result.current.data).toEqual([undefined, undefined, undefined]);

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.data).toEqual(mockData);
      expect(result.current.isSuccess).toBe(true);
      expect(result.current.isError).toBe(false);

      expect(mockFetchFn).toHaveBeenCalledTimes(3);
      expect(mockFetchFn).toHaveBeenCalledWith('urn1');
      expect(mockFetchFn).toHaveBeenCalledWith('urn2');
      expect(mockFetchFn).toHaveBeenCalledWith('urn3');
    });

    it('should return empty data when urns array is empty', () => {
      const { result } = renderHook(
        () =>
          useBatchGet({
            urns: [],
            fetchFn: mockFetchFn,
            queryKeyPrefix: 'test-items',
          }),
        {
          wrapper: createWrapper(),
        }
      );

      expect(result.current.data).toEqual([]);
      expect(result.current.isLoading).toBe(false);
      expect(result.current.isPending).toBe(true);
      expect(mockFetchFn).not.toHaveBeenCalled();
    });

    it('should not fetch when enabled is false', () => {
      const { result } = renderHook(
        () =>
          useBatchGet({
            urns: ['urn1', 'urn2'],
            fetchFn: mockFetchFn,
            queryKeyPrefix: 'test-items',
            enabled: false,
          }),
        {
          wrapper: createWrapper(),
        }
      );

      expect(result.current.isPending).toBe(true);
      expect(mockFetchFn).not.toHaveBeenCalled();
    });
  });

  describe('Individual URN Caching', () => {
    it('should only fetch new URNs when urns array changes', async () => {
      const mockData1: TestItem = { id: 'urn1', name: 'Item 1', value: 100 };
      const mockData2: TestItem = { id: 'urn2', name: 'Item 2', value: 200 };
      const mockData3: TestItem = { id: 'urn3', name: 'Item 3', value: 300 };

      mockFetchFn.mockResolvedValueOnce(mockData1).mockResolvedValueOnce(mockData2);

      // First render with urn1 and urn2
      const { result, rerender } = renderHook(
        ({ urns }: { urns: string[] }) =>
          useBatchGet({
            urns,
            fetchFn: mockFetchFn,
            queryKeyPrefix: 'test-items',
          }),
        {
          wrapper: createWrapper(),
          initialProps: { urns: ['urn1', 'urn2'] },
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.data).toEqual([mockData1, mockData2]);
      expect(mockFetchFn).toHaveBeenCalledTimes(2);

      // Add urn3 to the array
      mockFetchFn.mockResolvedValueOnce(mockData3);
      rerender({ urns: ['urn1', 'urn2', 'urn3'] });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Should only fetch urn3, not refetch urn1 and urn2
      expect(result.current.data).toEqual([mockData1, mockData2, mockData3]);
      expect(mockFetchFn).toHaveBeenCalledTimes(3); // Only urn3 was fetched again
      expect(mockFetchFn).toHaveBeenLastCalledWith('urn3');
    });

    it('should maintain order of results when urns are reordered', async () => {
      const mockData1: TestItem = { id: 'urn1', name: 'Item 1', value: 100 };
      const mockData2: TestItem = { id: 'urn2', name: 'Item 2', value: 200 };
      const mockData3: TestItem = { id: 'urn3', name: 'Item 3', value: 300 };

      mockFetchFn
        .mockResolvedValueOnce(mockData1)
        .mockResolvedValueOnce(mockData2)
        .mockResolvedValueOnce(mockData3);

      const { result, rerender } = renderHook(
        ({ urns }: { urns: string[] }) =>
          useBatchGet({
            urns,
            fetchFn: mockFetchFn,
            queryKeyPrefix: 'test-items',
          }),
        {
          wrapper: createWrapper(),
          initialProps: { urns: ['urn1', 'urn2', 'urn3'] },
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.data).toEqual([mockData1, mockData2, mockData3]);

      // Reorder urns
      rerender({ urns: ['urn3', 'urn1', 'urn2'] });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Results should be in the new order
      expect(result.current.data).toEqual([mockData3, mockData1, mockData2]);
      expect(mockFetchFn).toHaveBeenCalledTimes(3); // No additional fetches
    });

    it('should handle duplicate URNs correctly', async () => {
      const mockData: TestItem = { id: 'urn1', name: 'Item 1', value: 100 };

      mockFetchFn.mockResolvedValue(mockData);

      const { result } = renderHook(
        () =>
          useBatchGet({
            urns: ['urn1', 'urn1', 'urn1'],
            fetchFn: mockFetchFn,
            queryKeyPrefix: 'test-items',
          }),
        {
          wrapper: createWrapper(),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.data).toEqual([mockData, mockData, mockData]);
      expect(mockFetchFn).toHaveBeenCalledTimes(1);
    });
  });

  describe('Error Handling', () => {
    it('should handle individual query errors', async () => {
      const mockData: TestItem = { id: 'urn1', name: 'Item 1', value: 100 };
      const mockData3: TestItem = { id: 'urn3', name: 'Item 3', value: 300 };
      const error = new Error('Failed to fetch urn2');

      mockFetchFn
        .mockResolvedValueOnce(mockData)
        .mockRejectedValueOnce(error)
        .mockResolvedValueOnce(mockData3);

      const { result } = renderHook(
        () =>
          useBatchGet({
            urns: ['urn1', 'urn2', 'urn3'],
            fetchFn: mockFetchFn,
            queryKeyPrefix: 'test-items',
          }),
        {
          wrapper: createWrapper(),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.isError).toBe(true);
      expect(result.current.errors).toEqual([undefined, error, undefined]);
      expect(result.current.data).toEqual([mockData, undefined, mockData3]);
    });

    it('should handle all queries failing', async () => {
      const error1 = new Error('Failed to fetch urn1');
      const error2 = new Error('Failed to fetch urn2');

      mockFetchFn.mockRejectedValueOnce(error1).mockRejectedValueOnce(error2);

      const { result } = renderHook(
        () =>
          useBatchGet({
            urns: ['urn1', 'urn2'],
            fetchFn: mockFetchFn,
            queryKeyPrefix: 'test-items',
          }),
        {
          wrapper: createWrapper(),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.isError).toBe(true);
      expect(result.current.errors).toEqual([error1, error2]);
      expect(result.current.data).toEqual([undefined, undefined]);
    });
  });

  describe('Loading States', () => {
    it('should show loading when any query is loading', async () => {
      let resolveFirst: (value: TestItem) => void;
      let resolveSecond: (value: TestItem) => void;

      const firstPromise = new Promise<TestItem>((resolve) => {
        resolveFirst = resolve;
      });
      const secondPromise = new Promise<TestItem>((resolve) => {
        resolveSecond = resolve;
      });

      mockFetchFn.mockReturnValueOnce(firstPromise).mockReturnValueOnce(secondPromise);

      const { result } = renderHook(
        () =>
          useBatchGet({
            urns: ['urn1', 'urn2'],
            fetchFn: mockFetchFn,
            queryKeyPrefix: 'test-items',
          }),
        {
          wrapper: createWrapper(),
        }
      );

      expect(result.current.isLoading).toBe(true);

      // Resolve first query
      resolveFirst!({ id: 'urn1', name: 'Item 1', value: 100 });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(true); // Still loading because second query is pending
      });

      // Resolve second query
      resolveSecond!({ id: 'urn2', name: 'Item 2', value: 200 });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });
      expect(result.current.isSuccess).toBe(true);
    });

    it('should show success when all queries complete successfully', async () => {
      const mockData: TestItem[] = [
        { id: 'urn1', name: 'Item 1', value: 100 },
        { id: 'urn2', name: 'Item 2', value: 200 },
      ];

      mockFetchFn.mockResolvedValueOnce(mockData[0]).mockResolvedValueOnce(mockData[1]);

      const { result } = renderHook(
        () =>
          useBatchGet({
            urns: ['urn1', 'urn2'],
            fetchFn: mockFetchFn,
            queryKeyPrefix: 'test-items',
          }),
        {
          wrapper: createWrapper(),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.isSuccess).toBe(true);
      expect(result.current.isError).toBe(false);
      expect(result.current.data).toEqual(mockData);
    });
  });

  describe('Refetch Functionality', () => {
    it('should refetch all queries when refetch is called', async () => {
      const mockData: TestItem[] = [
        { id: 'urn1', name: 'Item 1', value: 100 },
        { id: 'urn2', name: 'Item 2', value: 200 },
      ];

      mockFetchFn
        .mockResolvedValueOnce(mockData[0])
        .mockResolvedValueOnce(mockData[1])
        .mockResolvedValueOnce(mockData[0])
        .mockResolvedValueOnce(mockData[1]);

      const { result } = renderHook(
        () =>
          useBatchGet({
            urns: ['urn1', 'urn2'],
            fetchFn: mockFetchFn,
            queryKeyPrefix: 'test-items',
          }),
        {
          wrapper: createWrapper(),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(mockFetchFn).toHaveBeenCalledTimes(2);

      // Call refetch
      result.current.refetch();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Should have been called 4 times total (2 initial + 2 refetch)
      expect(mockFetchFn).toHaveBeenCalledTimes(4);
    });
  });

  describe('Query Options', () => {
    it('should pass through query options to individual queries', async () => {
      const mockData: TestItem = { id: 'urn1', name: 'Item 1', value: 100 };
      mockFetchFn.mockResolvedValue(mockData);

      const { result } = renderHook(
        () =>
          useBatchGet({
            urns: ['urn1'],
            fetchFn: mockFetchFn,
            queryKeyPrefix: 'test-items',
            staleTime: 5000,
            retry: 3,
          }),
        {
          wrapper: createWrapper(),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.data).toEqual([mockData]);
      expect(mockFetchFn).toHaveBeenCalledTimes(1);
    });
  });

  describe('Data Ordering', () => {
    it('should return data in the same order as input URNs even when queries resolve out of order', async () => {
      let resolveSecond: (value: TestItem) => void;
      let resolveFirst: (value: TestItem) => void;

      const firstPromise = new Promise<TestItem>((resolve) => {
        resolveFirst = resolve;
      });
      const secondPromise = new Promise<TestItem>((resolve) => {
        resolveSecond = resolve;
      });

      mockFetchFn.mockReturnValueOnce(firstPromise).mockReturnValueOnce(secondPromise);

      const { result } = renderHook(
        () =>
          useBatchGet({
            urns: ['urn1', 'urn2'],
            fetchFn: mockFetchFn,
            queryKeyPrefix: 'test-items',
          }),
        {
          wrapper: createWrapper(),
        }
      );

      // Resolve second query first
      resolveSecond!({ id: 'urn2', name: 'Item 2', value: 200 });

      // Resolve first query second
      resolveFirst!({ id: 'urn1', name: 'Item 1', value: 100 });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Data should still be in the original order
      expect(result.current.data).toEqual([
        { id: 'urn1', name: 'Item 1', value: 100 },
        { id: 'urn2', name: 'Item 2', value: 200 },
      ]);
    });
  });
});
