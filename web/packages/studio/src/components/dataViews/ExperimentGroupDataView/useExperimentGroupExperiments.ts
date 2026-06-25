// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useToast } from '@nemo/common/src/providers/toast/useToast';
import {
  getListExperimentsQueryKey,
  type ListExperimentsQueryError,
  useListExperiments,
  usePinExperiment,
  useUnpinExperiment,
} from '@nemo/sdk/generated/platform/api';
import type {
  ExperimentFilter,
  ExperimentResponse,
  ListExperimentsParams,
} from '@nemo/sdk/generated/platform/schema';
import { keepPreviousData, useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo, useRef } from 'react';

/** An API response plus the stable `id` the data view needs. */
export type ExperimentRow = ExperimentResponse & { id: string };
export type ListExperimentsSortParam = NonNullable<ListExperimentsParams['sort']>;

const toRows = (experiments: ExperimentResponse[] | undefined): ExperimentRow[] =>
  (experiments ?? []).map((experiment) => ({
    ...experiment,
    id: experiment.id ?? experiment.name ?? '',
  }));

/**
 * Pinned rows are shown in full atop every page rather than paginated, so the whole pin set is
 * fetched in one request. A group's pin set is a small curated list; this bound keeps that request
 * well under the API's max page size (1000) while covering any realistic number of pins.
 */
const MAX_PINNED_ROWS = 100;

export interface UseExperimentGroupExperimentsParams {
  workspace: string;
  experimentGroupId: string;
  filter: Partial<ExperimentFilter> | undefined;
  search: string;
  page: number;
  pageSize: number;
  sort: ListExperimentsSortParam;
}

export interface ExperimentGroupExperiments {
  /** Pinned rows first (newest-pinned first), then the current page of unpinned rows. */
  rows: ExperimentRow[];
  /** Pins the row if unpinned, unpins it otherwise, then refetches both lists. */
  togglePin: (row: ExperimentRow) => void;
  /**
   * Row count that drives pagination: the unpinned total. Pinned rows ride atop every page and are
   * not paginated, so they're excluded; falls back to the pinned count when nothing is unpinned so
   * a fully-pinned group still renders one page instead of reading as empty.
   */
  totalCount: number;
  error: ListExperimentsQueryError | null;
  /** True until both queries have loaded once; ignores background refetches (page changes, pins). */
  isLoading: boolean;
  /** True when either query is fetching */
  isFetching: boolean;
}

/**
 * Loads one experiment group's experiments as two queries — the full pinned set (`is_pinned=true`,
 * sorted `-pinned_at`) and the current page of unpinned (`is_pinned=false`) — and concatenates them
 * so pinned rows top every page. Pagination covers only the unpinned set; the pinned set is fetched
 * once and repeated atop every page rather than paginated. A pin/unpin persists through the API,
 * then invalidates both lists so the new state is refetched (no optimistic update).
 */
export function useExperimentGroupExperiments({
  workspace,
  experimentGroupId,
  filter,
  search,
  page,
  pageSize,
  sort,
}: UseExperimentGroupExperimentsParams): ExperimentGroupExperiments {
  const queryClient = useQueryClient();
  const toast = useToast();

  const baseFilter = {
    ...filter,
    ...(search && { name: { $like: search } }),
    // Spread last so the group scope can't be overridden by a user filter.
    experiment_group_id: experimentGroupId,
  };
  const listQueryOptions = {
    query: {
      placeholderData: keepPreviousData,
      enabled: !!experimentGroupId,
    },
  };

  const {
    data: pinnedResponse,
    isLoading: isPinnedLoading,
    isFetching: isPinnedFetching,
    error: pinnedError,
  } = useListExperiments(
    workspace,
    {
      page: 1,
      page_size: MAX_PINNED_ROWS,
      sort: '-pinned_at',
      filter: { ...baseFilter, is_pinned: true } as ExperimentFilter,
    },
    listQueryOptions
  );

  const {
    data: unpinnedResponse,
    isLoading: isUnpinnedLoading,
    isFetching: isUnpinnedFetching,
    error: unpinnedError,
  } = useListExperiments(
    workspace,
    {
      page,
      page_size: pageSize,
      sort,
      filter: { ...baseFilter, is_pinned: false } as ExperimentFilter,
    },
    listQueryOptions
  );

  const pinned = useMemo(() => toRows(pinnedResponse?.data), [pinnedResponse]);
  const unpinned = useMemo(() => toRows(unpinnedResponse?.data), [unpinnedResponse]);

  // Synchronous guard so a row can't fire a second pin/unpin while one is already in flight; the
  // name is cleared once the mutation settles.
  const pendingRef = useRef<Set<string>>(new Set());

  // Scope invalidation to this group's experiment lists (any page/sort/filter, pinned and unpinned)
  // via a partial key match on experiment_group_id, so a pin/unpin doesn't refetch other groups'
  // lists. Returned (not voided) so the mutation's onSuccess awaits the refetch before onSettled
  // re-enables the row.
  const invalidateList = useCallback(
    () =>
      queryClient.invalidateQueries({
        queryKey: getListExperimentsQueryKey(workspace, {
          filter: { experiment_group_id: experimentGroupId },
        }),
      }),
    [queryClient, workspace, experimentGroupId]
  );

  const { mutate: pinExperiment } = usePinExperiment({
    mutation: {
      onSuccess: invalidateList,
      onError: () => toast.error('Failed to pin experiment.'),
      onSettled: (_data, _error, { name }) => {
        pendingRef.current.delete(name);
      },
    },
  });
  const { mutate: unpinExperiment } = useUnpinExperiment({
    mutation: {
      onSuccess: invalidateList,
      onError: () => toast.error('Failed to unpin experiment.'),
      onSettled: (_data, _error, { name }) => {
        pendingRef.current.delete(name);
      },
    },
  });

  const togglePin = useCallback(
    (row: ExperimentRow) => {
      const { name } = row;
      if (pendingRef.current.has(name)) return;
      pendingRef.current.add(name);
      if (row.pinned_at != null) unpinExperiment({ workspace, name });
      else pinExperiment({ workspace, name });
    },
    [workspace, pinExperiment, unpinExperiment]
  );

  // Pinned first, then the current page of unpinned. Drop any unpinned row already shown as pinned —
  // it can appear in both server lists during the brief window where the two queries refetch out of step.
  const rows = useMemo<ExperimentRow[]>(() => {
    const pinnedNames = new Set(pinned.map((row) => row.name));
    return [...pinned, ...unpinned.filter((row) => !pinnedNames.has(row.name))];
  }, [pinned, unpinned]);

  // Pagination covers the unpinned set only — pinned rows are a fixed header repeated atop every
  // page, so counting them would inflate the page count and add trailing pages that show nothing
  // but the (already-visible) pinned rows. Fall back to the pinned count when nothing is unpinned so
  // a fully-pinned group still renders a single page instead of reading as empty.
  const unpinnedTotal = unpinnedResponse?.pagination?.total_results ?? unpinned.length;
  const totalCount = unpinnedTotal > 0 ? unpinnedTotal : pinned.length;
  const error = pinnedError ?? unpinnedError;
  // react-query's per-query isLoading is true only on first load (keepPreviousData keeps data across
  // refetches, so isPending stays false). OR-ing the two keeps the table in its loading state until
  // both lists have loaded once, rather than clearing as soon as the faster query returns.
  const isLoading = isPinnedLoading || isUnpinnedLoading;
  const isFetching = isPinnedFetching || isUnpinnedFetching;

  return { rows, togglePin, totalCount, error, isLoading, isFetching };
}
