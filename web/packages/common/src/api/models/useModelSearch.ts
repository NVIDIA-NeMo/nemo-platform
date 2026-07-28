// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { WithFilterOperators } from '@nemo/common/src/api/filterOperators';
import { useModelsInfinite, type ModelWorkspaceGroup } from '@nemo/common/src/api/models/useModels';
import { groupModelsByWorkspace } from '@nemo/common/src/utils/models';
import {
  type ModelEntity,
  ModelEntitySortField,
  type ModelEntityFilter,
} from '@nemo/sdk/generated/platform/schema';
import { useCallback, useEffect, useMemo, useState } from 'react';

/**
 * Page size for search-as-you-type model lists. Small on purpose: the dropdown pulls the next
 * page as the user scrolls, so the first page needs to arrive fast, not be complete.
 */
export const MODEL_SEARCH_PAGE_SIZE = 25;

export type ModelSearchFilter = WithFilterOperators<ModelEntityFilter>;

export interface UseModelSearchOptions {
  /** Workspace to search. The query stays idle while this is null. */
  workspace: string | null;
  /** Extra filters merged into the request (e.g. `lora_enabled`, `base_model`). */
  filter?: ModelSearchFilter;
  sort?: ModelEntitySortField;
  pageSize?: number;
  enabled?: boolean;
  /**
   * Client-side predicate applied to every page — for conditions the API cannot express, such as
   * "has a ready deployment" (`model_providers.length > 0`). The hook keeps paging while a page
   * filters down to nothing, so an excluded page never stalls the list.
   */
  include?: (model: ModelEntity) => boolean;
}

/**
 * Props for `ModelSelectV2`, ready to spread. Every field lines up with a prop name so a caller
 * that needs nothing custom is a single line.
 */
export interface ModelSearchProps {
  groups: ModelWorkspaceGroup[];
  loading: boolean;
  onSearchChange: (search: string) => void;
  onLoadMore: () => Promise<void>;
  hasMore: boolean;
  isLoadingMore: boolean;
}

export interface UseModelSearchResult extends ModelSearchProps {
  models: ModelEntity[];
  search: string;
  error: Error | null;
}

/**
 * Server-side model search with progressive paging — the counterpart to `useAllModels`, which
 * walks every page up front. Filtering happens in the API and pages arrive as the user scrolls,
 * so a workspace with thousands of models costs one small request at a time.
 *
 * @example
 * const [open, setOpen] = useState(false);
 * const models = useModelSearch({ workspace, enabled: open });
 * return <ModelSelectV2 {...models} value={value} onValueChange={onChange} onOpenChange={setOpen} />;
 */
export const useModelSearch = ({
  workspace,
  filter,
  sort = ModelEntitySortField.name,
  pageSize = MODEL_SEARCH_PAGE_SIZE,
  enabled = true,
  include,
}: UseModelSearchOptions): UseModelSearchResult => {
  const [search, setSearch] = useState('');

  const query = useMemo(() => {
    const trimmed = search.trim();
    const merged: ModelSearchFilter = {
      ...filter,
      ...(trimmed ? { name: { $like: trimmed } } : {}),
    };
    return {
      page_size: pageSize,
      sort,
      ...(Object.keys(merged).length > 0 ? { filter: merged as ModelEntityFilter } : {}),
    };
  }, [filter, pageSize, search, sort]);

  const isEnabled = enabled && !!workspace;
  const { data, error, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading } =
    useModelsInfinite({
      workspace: workspace ?? undefined,
      query,
      queryOptions: { enabled: isEnabled },
    });

  const models = useMemo(() => {
    const loaded = data?.pages.flatMap((page) => page.data ?? []) ?? [];
    return include ? loaded.filter(include) : loaded;
  }, [data?.pages, include]);

  const groups = useMemo(() => groupModelsByWorkspace(models, { sort: true }), [models]);

  const hasMore = !!hasNextPage;

  const onLoadMore = useCallback(async () => {
    if (!hasNextPage || isFetchingNextPage) return;
    await fetchNextPage();
  }, [fetchNextPage, hasNextPage, isFetchingNextPage]);

  // `include` can empty a whole page, leaving the list with no rows to scroll and therefore no way
  // to ask for the next one. Keep paging until something survives the filter.
  useEffect(() => {
    if (isEnabled && models.length === 0 && hasNextPage && !isFetchingNextPage && !isLoading) {
      void fetchNextPage();
    }
  }, [fetchNextPage, hasNextPage, isEnabled, isFetchingNextPage, isLoading, models.length]);

  return {
    models,
    groups,
    search,
    error,
    loading: isLoading,
    onSearchChange: setSearch,
    onLoadMore,
    hasMore,
    isLoadingMore: isFetchingNextPage,
  };
};
