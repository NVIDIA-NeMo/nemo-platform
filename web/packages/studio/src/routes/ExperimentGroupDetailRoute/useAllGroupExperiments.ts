// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { listExperiments } from '@nemo/sdk/generated/platform/api';
import type {
  ExperimentResponse,
  ExperimentResponsesPage,
} from '@nemo/sdk/generated/platform/schema';
import { useInfiniteQuery } from '@tanstack/react-query';
import { useEffect, useMemo } from 'react';

const PAGE_SIZE = 100;

interface UseAllGroupExperimentsResult {
  experiments: ExperimentResponse[];
  isFetching: boolean;
}

/** Fetches every experiment belonging to a group, auto-paging until exhausted. */
export const useAllGroupExperiments = (
  workspace: string,
  experimentGroupId: string
): UseAllGroupExperimentsResult => {
  const { data, isFetching, isError, hasNextPage, fetchNextPage } = useInfiniteQuery({
    queryKey: ['experiment-group-experiments', workspace, experimentGroupId],
    queryFn: ({ pageParam, signal }) =>
      listExperiments(
        workspace,
        {
          page: pageParam,
          page_size: PAGE_SIZE,
          filter: { experiment_group_id: experimentGroupId },
        },
        signal
      ),
    initialPageParam: 1,
    getNextPageParam: (lastPage: ExperimentResponsesPage) => {
      const { page, total_pages } = lastPage.pagination ?? {};
      return page !== undefined && total_pages !== undefined && page < total_pages
        ? page + 1
        : undefined;
    },
    enabled: !!experimentGroupId,
  });

  useEffect(() => {
    if (!isFetching && !isError && hasNextPage) {
      void fetchNextPage();
    }
  }, [isFetching, isError, hasNextPage, fetchNextPage]);

  const experiments = useMemo(() => data?.pages.flatMap((page) => page.data) ?? [], [data?.pages]);

  return { experiments, isFetching };
};
