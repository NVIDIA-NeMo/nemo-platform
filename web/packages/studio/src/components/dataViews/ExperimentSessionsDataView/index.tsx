// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  Root as DataViewRoot,
  EditColumnsMenu,
} from '@nemo/common/src/components/DataView/internal';
import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { snakeCaseToTitleCase } from '@nemo/common/src/utils/formatters';
import { useGetExperiment, useListExperimentSessions } from '@nemo/sdk/generated/platform/api';
import type {
  ExperimentSessionFilter,
  ExperimentSessionResponse,
} from '@nemo/sdk/generated/platform/schema';
import { Text, Tooltip } from '@nvidia/foundations-react-core';
import { Empty } from '@studio/components/dataViews/ExperimentSessionsDataView/Empty';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getExperimentTraceDetailRoute } from '@studio/routes/utils';
import { tooltipClassName } from '@studio/styles/common';
import { keepPreviousData } from '@tanstack/react-query';
import { Columns3 } from 'lucide-react';
import { type ComponentProps, type FC, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';

type SessionRow = ExperimentSessionResponse & { _rowId: string };

interface ExperimentSessionsDataViewProps {
  experimentName: string;
  experimentGroupName: string;
}

const mapStatusForBadge = (status: ExperimentSessionResponse['status']) =>
  status === 'success' ? 'completed' : status;

const formatScore = (value: number): string => `${(value * 100).toFixed(1)}%`;

export const ExperimentSessionsDataView: FC<ExperimentSessionsDataViewProps> = ({
  experimentName,
  experimentGroupName,
}) => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const dataViewState = useStudioDataViewState<ExperimentSessionFilter>({ columnVisibility: {} });
  const { data: experiment } = useGetExperiment(workspace, experimentName);

  const page = dataViewState.pagination.state.pageIndex + 1;
  const pageSize = dataViewState.pagination.state.pageSize;

  const { data: sessionsResponse, isLoading } = useListExperimentSessions(
    workspace,
    experimentName,
    {
      page,
      page_size: pageSize,
      filter: {
        ...dataViewState.apiFilter.filter,
        ...(dataViewState.debouncedSearchBar && {
          test_case_id: dataViewState.debouncedSearchBar,
        }),
      },
    },
    { query: { placeholderData: keepPreviousData } }
  );

  const sessionsData = sessionsResponse?.data;
  const totalCount = sessionsResponse?.pagination?.total_results ?? sessionsData?.length ?? 0;

  const tableData = useMemo<SessionRow[]>(
    () =>
      (sessionsData ?? []).map((session, i) => ({
        ...session,
        _rowId: session.session_id ?? String(i),
      })),
    [sessionsData]
  );

  // Client-side status filter for instant feedback while the debounced API request catches up.
  const immediateStatusFilter = dataViewState.columnFiltering.state.find((f) => f.id === 'status')
    ?.value as string | undefined;
  const visibleTableData = useMemo(
    () =>
      immediateStatusFilter
        ? tableData.filter((row) => row.status === immediateStatusFilter)
        : tableData,
    [tableData, immediateStatusFilter]
  );

  // One column per evaluator. The experiment's `evaluator_names` is the
  // authoritative, stable set across all sessions; we union in any score keys
  // present in the current page's data so a column never goes missing while the
  // experiment is still loading. Sorted for deterministic column ordering.
  const evaluatorNames = useMemo<string[]>(() => {
    const names = new Set<string>(experiment?.evaluator_names ?? []);
    for (const session of sessionsData ?? []) {
      for (const name of Object.keys(session.evaluator_scores ?? {})) {
        names.add(name);
      }
    }
    return Array.from(names).sort();
  }, [experiment?.evaluator_names, sessionsData]);

  const makeColumns: ComponentProps<typeof DataViewRoot<SessionRow>>['makeColumns'] = ({
    accessor,
  }) => [
    accessor('test_case_id', {
      header: 'Case',
      enableSorting: false,
      size: 200,
      cell: ({ row }) => {
        const value = row.original.test_case_id;
        if (!value) return <Text>-</Text>;
        return (
          <Tooltip slotContent={value} className={tooltipClassName} side="bottom">
            <Text className="cursor-default truncate max-w-[180px] block">{value}</Text>
          </Tooltip>
        );
      },
    }),
    accessor('input', {
      header: 'Input',
      enableSorting: false,
      size: 240,
      cell: ({ row }) => {
        const value = row.original.input;
        if (!value) return <Text>-</Text>;
        return (
          <Tooltip slotContent={value} className={tooltipClassName} side="bottom">
            <Text className="cursor-default truncate max-w-[220px] block">{value}</Text>
          </Tooltip>
        );
      },
    }),
    accessor('started_at', {
      header: 'Started at',
      enableSorting: false,
      cell: ({ row }) =>
        row.original.started_at ? (
          <RelativeTime datetime={row.original.started_at} />
        ) : (
          <Text>-</Text>
        ),
    }),
    accessor('ended_at', {
      header: 'Ended at',
      enableSorting: false,
      cell: ({ row }) =>
        row.original.ended_at ? <RelativeTime datetime={row.original.ended_at} /> : <Text>-</Text>,
    }),
    accessor('latency_ms', {
      header: 'Latency',
      enableSorting: false,
      cell: ({ row }) => {
        const ms = row.original.latency_ms;
        return <Text>{ms != null ? `${Math.round(ms)} ms` : '-'}</Text>;
      },
    }),
    accessor('status', {
      header: 'Status',
      enableSorting: false,
      meta: {
        filter: {
          type: 'single-select',
          label: 'Status',
          options: [
            { value: 'success', label: 'Completed' },
            { value: 'error', label: 'Error' },
            { value: 'cancelled', label: 'Cancelled' },
            { value: 'unknown', label: 'Unknown' },
          ],
        },
      },
      cell: ({ row }) => <StatusBadge status={mapStatusForBadge(row.original.status)} />,
    }),
    accessor(
      (original) =>
        original.input_tokens != null || original.output_tokens != null
          ? (original.input_tokens ?? 0) + (original.output_tokens ?? 0)
          : undefined,
      {
        id: 'tokens',
        header: 'Tokens',
        enableSorting: false,
        cell: ({ row }) => {
          const { input_tokens, output_tokens } = row.original;
          if (input_tokens == null && output_tokens == null) return <Text>-</Text>;
          return <Text>{String((input_tokens ?? 0) + (output_tokens ?? 0))}</Text>;
        },
      }
    ),
    accessor('cost_total_usd', {
      header: 'Cost',
      enableSorting: false,
      cell: ({ row }) => {
        const cost = row.original.cost_total_usd;
        return <Text>{cost != null ? `$${cost.toFixed(3)}` : '-'}</Text>;
      },
    }),
    ...evaluatorNames.map((name, index) =>
      accessor((original) => original.evaluator_scores?.[name], {
        id: `score-${index}`,
        header: snakeCaseToTitleCase(name),
        enableSorting: false,
        size: 130,
        cell: ({ row }) => {
          const value = row.original.evaluator_scores?.[name];
          return <Text>{value != null ? formatScore(value) : '-'}</Text>;
        },
      })
    ),
  ];

  return (
    <StudioDataView
      dataViewState={dataViewState}
      makeColumns={makeColumns}
      searchField="test_case_id"
      onRowClick={(row) => {
        if (row.trace_id) {
          navigate(
            getExperimentTraceDetailRoute(
              workspace,
              experimentGroupName,
              experimentName,
              row.trace_id
            )
          );
        }
      }}
      toolbarSlotEnd={
        <EditColumnsMenu
          kind="secondary"
          showChevron={false}
          slotContent={<div aria-hidden className="h-0 w-[230px]" />}
        >
          <>
            <Columns3 />
            <span className="hide-mobile">Columns</span>
          </>
        </EditColumnsMenu>
      }
      attributes={{
        DataViewRoot: {
          data: visibleTableData,
          totalCount,
          requestStatus: isLoading && !sessionsData ? 'loading' : undefined,
        },
        DataViewSearchBar: { placeholder: 'Search case...' },
        DataViewTableContent: {
          renderEmptyState: () => {
            const hasActiveFilters =
              !!dataViewState.searchBar.state || dataViewState.columnFiltering.state.length > 0;
            if (hasActiveFilters) {
              return (
                <TableEmptyState
                  header="No matching test cases"
                  emptyMessage={
                    <>
                      Change your filters and try again, or{' '}
                      <button
                        className="text-content-link hover:underline"
                        onClick={dataViewState.resetFilters}
                      >
                        clear filters
                      </button>
                      .
                    </>
                  }
                />
              );
            }
            return (
              <Empty
                experimentGroupName={experimentGroupName}
                datasetName={experiment?.dataset_name ?? '<dataset>'}
              />
            );
          },
        },
      }}
    />
  );
};
