// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useAllModels } from '@nemo/common/src/api/models/useModels';
import type { ModelEntity, ModelEntitysPage } from '@nemo/sdk/generated/platform/schema';
import { useModelLoraEnabled } from '@studio/hooks/useModelLoraEnabled';
import { renderHook } from '@testing-library/react';

vi.mock('@nemo/common/src/api/models/useModels', () => ({
  useAllModels: vi.fn(),
}));

const mockedUseAllModels = vi.mocked(useAllModels);

/**
 * `useAllModels` returns a `useInfiniteQuery` result. The hook only touches
 * `data.pages`, `isFetching`, and `hasNextPage` — cast through `unknown` so
 * tests stay focused on the contract we actually depend on.
 */
const queryResult = (
  pages: ModelEntitysPage[] | undefined,
  flags: { isFetching?: boolean; hasNextPage?: boolean } = {}
): ReturnType<typeof useAllModels> =>
  ({
    data: pages !== undefined ? { pages, pageParams: [] } : undefined,
    isFetching: flags.isFetching ?? false,
    hasNextPage: flags.hasNextPage ?? false,
  }) as unknown as ReturnType<typeof useAllModels>;

const buildModel = (overrides: Partial<ModelEntity> = {}): ModelEntity =>
  ({
    id: 'model-1',
    name: 'my-model',
    workspace: 'ws',
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
    ...overrides,
  }) as ModelEntity;

const page = (results: ModelEntity[]): ModelEntitysPage =>
  ({ data: results }) as unknown as ModelEntitysPage;

describe('useModelLoraEnabled', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedUseAllModels.mockReturnValue(queryResult(undefined));
  });

  it('returns isLoraEnabled=false and disables the query when model is undefined', () => {
    const { result } = renderHook(() => useModelLoraEnabled(undefined));

    expect(result.current).toEqual({ isLoraEnabled: false, isLoading: false });
    expect(mockedUseAllModels).toHaveBeenCalledWith(
      expect.objectContaining({
        workspace: '',
        queryOptions: expect.objectContaining({ enabled: false }),
      })
    );
  });

  it('queries the workspace-wide lora-enabled set without a name filter', () => {
    renderHook(() => useModelLoraEnabled(buildModel()));

    expect(mockedUseAllModels).toHaveBeenCalledWith(
      expect.objectContaining({
        workspace: 'ws',
        query: expect.objectContaining({
          filter: { lora_enabled: true },
          page_size: 1000,
        }),
        queryOptions: expect.objectContaining({ enabled: true }),
      })
    );
  });

  it('reports isLoraEnabled=true when the model is in the returned set', () => {
    mockedUseAllModels.mockReturnValue(
      queryResult([page([buildModel({ name: 'other-model' }), buildModel({ name: 'my-model' })])])
    );

    const { result } = renderHook(() => useModelLoraEnabled(buildModel()));

    expect(result.current.isLoraEnabled).toBe(true);
  });

  it('aggregates names across multiple pages (auto-pagination)', () => {
    mockedUseAllModels.mockReturnValue(
      queryResult([
        page([buildModel({ name: 'page-1-model' })]),
        page([buildModel({ name: 'page-2-model' }), buildModel({ name: 'my-model' })]),
      ])
    );

    const { result } = renderHook(() => useModelLoraEnabled(buildModel()));

    expect(result.current.isLoraEnabled).toBe(true);
  });

  it('reports isLoraEnabled=false when the model is absent from every page', () => {
    mockedUseAllModels.mockReturnValue(queryResult([page([buildModel({ name: 'someone-else' })])]));

    const { result } = renderHook(() => useModelLoraEnabled(buildModel()));

    expect(result.current.isLoraEnabled).toBe(false);
  });

  it('reports isLoraEnabled=false when the workspace has no lora-enabled models', () => {
    mockedUseAllModels.mockReturnValue(queryResult([page([])]));

    const { result } = renderHook(() => useModelLoraEnabled(buildModel()));

    expect(result.current.isLoraEnabled).toBe(false);
  });

  it('isLoading=true while the current page is fetching', () => {
    mockedUseAllModels.mockReturnValue(queryResult(undefined, { isFetching: true }));

    const { result } = renderHook(() => useModelLoraEnabled(buildModel()));

    expect(result.current.isLoading).toBe(true);
  });

  it('isLoading=true between pages when more pages remain (hasNextPage)', () => {
    // Defends against a partial-result race: a page just landed (isFetching
    // momentarily false) but more pages are still queued.
    mockedUseAllModels.mockReturnValue(
      queryResult([page([buildModel({ name: 'first-page' })])], {
        isFetching: false,
        hasNextPage: true,
      })
    );

    const { result } = renderHook(() => useModelLoraEnabled(buildModel()));

    expect(result.current.isLoading).toBe(true);
  });

  it('does not surface isLoading when the model is missing (query is disabled)', () => {
    mockedUseAllModels.mockReturnValue(
      queryResult(undefined, { isFetching: true, hasNextPage: true })
    );

    const { result } = renderHook(() => useModelLoraEnabled(undefined));

    expect(result.current.isLoading).toBe(false);
  });
});
