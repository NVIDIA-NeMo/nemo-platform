/*
 * SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

import { withOperators } from '@nemo/common/src/api/filterOperators';
import {
  ControlledSearchableSelect,
  type SelectItemOption,
} from '@nemo/common/src/components/form/ControlledSearchableSelect';
import { filesListFilesets, getFilesListFilesetsQueryKey } from '@nemo/sdk/generated/platform/api';
import type { FilesListFilesetsParams } from '@nemo/sdk/generated/platform/schema';
import { useInfiniteQuery } from '@tanstack/react-query';
import { type ReactNode, useCallback, useMemo, useState } from 'react';
import { type FieldValues, type UseControllerProps } from 'react-hook-form';

const FILESETS_PAGE_SIZE = 20;

export type FilesetSearchableSelectFormFieldProps = {
  slotLabel?: ReactNode;
  slotInfo?: ReactNode;
  slotError?: string;
};

export type FilesetSearchableSelectProps<T extends FieldValues> = {
  workspace: string;
  queryEnabled?: boolean;
  useControllerProps: UseControllerProps<T>;
  formFieldProps: FilesetSearchableSelectFormFieldProps;
  triggerPlaceholder?: string;
};

export function FilesetSearchableSelect<T extends FieldValues>({
  workspace,
  queryEnabled = true,
  useControllerProps,
  formFieldProps,
  triggerPlaceholder = 'Select a fileset',
}: FilesetSearchableSelectProps<T>) {
  const [search, setSearch] = useState('');
  const filter = useMemo<FilesListFilesetsParams['filter'] | undefined>(() => {
    if (!search) return undefined;
    return withOperators<FilesListFilesetsParams['filter']>({
      name: { $like: `%${search}%` },
    });
  }, [search]);

  const {
    data: pages,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
  } = useInfiniteQuery({
    queryKey: [...getFilesListFilesetsQueryKey(workspace), 'infinite', 'newest', search] as const,
    queryFn: ({ signal, pageParam }) =>
      filesListFilesets(
        workspace,
        { page: pageParam, page_size: FILESETS_PAGE_SIZE, sort: '-created_at', filter },
        signal
      ),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => {
      const p = lastPage.pagination;
      return p && p.page < p.total_pages ? p.page + 1 : undefined;
    },
    enabled: queryEnabled && !!workspace,
  });

  const options: SelectItemOption[] = useMemo(() => {
    const list = pages?.pages.flatMap((page) => page.data) ?? [];
    return list.map((fs) => {
      const ref = `${fs.workspace}/${fs.name}`;
      return { value: ref, label: ref };
    });
  }, [pages?.pages]);

  const handleLoadMore = useCallback(async () => {
    if (hasNextPage && !isFetchingNextPage) await fetchNextPage();
  }, [fetchNextPage, hasNextPage, isFetchingNextPage]);

  return (
    <ControlledSearchableSelect
      useControllerProps={useControllerProps as unknown as UseControllerProps<FieldValues>}
      options={options}
      onSearchChange={setSearch}
      onLoadMore={handleLoadMore}
      hasMore={hasNextPage ?? false}
      isLoading={isLoading}
      isLoadingMore={isFetchingNextPage}
      searchPlaceholder="Search filesets..."
      emptyMessage="No filesets found"
      triggerPlaceholder={triggerPlaceholder}
      formFieldProps={formFieldProps}
    />
  );
}
