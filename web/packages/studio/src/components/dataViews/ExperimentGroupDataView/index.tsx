// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { dateTimeFilter } from '@nemo/common/src/components/DataView/dateTimeFilter';
import {
  Root as DataViewRoot,
  EditColumnsMenu,
} from '@nemo/common/src/components/DataView/internal';
import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { getSortParamWithWhitelist } from '@nemo/common/src/utils/query';
import { useGetExperimentGroup, useListExperiments } from '@nemo/sdk/generated/platform/api';
import type {
  ExperimentFilter,
  ExperimentResponse,
  ListExperimentsSort,
} from '@nemo/sdk/generated/platform/schema';
import { Text, Tooltip } from '@nvidia/foundations-react-core';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getExperimentDetailRoute } from '@studio/routes/utils';
import { tooltipClassName } from '@studio/styles/common';
import { keepPreviousData } from '@tanstack/react-query';
import { Columns3 } from 'lucide-react';
import { type ComponentProps, type FC, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';

export type ExperimentRow = ExperimentResponse & { id: string };

const SORTABLE_FIELDS = ['name', 'created_at'] as const;
const DEFAULT_SORT = '-created_at';

interface ExperimentGroupDataViewProps {
  experimentGroupName: string;
}

/** Formats an experiment's aggregate scores into a single average-percent string. */
const formatScores = (aggregateScores: ExperimentResponse['aggregate_scores']): string => {
  const means = Object.values(aggregateScores ?? {})
    .map((score) => score?.mean)
    .filter((mean): mean is number => mean !== undefined && mean !== null);
  if (means.length === 0) return '-';
  const avg = means.reduce((a, b) => a + b, 0) / means.length;
  return `${(avg * 100).toFixed(1)}%`;
};

/** Lists the experiments that belong to a single experiment group. */
export const ExperimentGroupDataView: FC<ExperimentGroupDataViewProps> = ({
  experimentGroupName,
}) => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const {
    data: group,
    isLoading: isGroupLoading,
    error: groupError,
  } = useGetExperimentGroup(workspace, experimentGroupName);
  const experimentGroupId = group?.id ?? '';

  const dataViewState = useStudioDataViewState<ExperimentFilter>({
    defaultSort: { id: 'created_at', desc: true },
    // created_by isn't returned by the API and updated_at isn't shown; both are filter-only.
    columnVisibility: { created_by: false, updated_at: false },
  });

  const page = dataViewState.pagination.state.pageIndex + 1;
  const pageSize = dataViewState.pagination.state.pageSize;
  const sortParam = getSortParamWithWhitelist(
    dataViewState.sorting.state,
    SORTABLE_FIELDS,
    DEFAULT_SORT
  );

  const {
    data: experimentsResponse,
    isLoading,
    error,
  } = useListExperiments(
    workspace,
    {
      page,
      page_size: pageSize,
      sort: sortParam as ListExperimentsSort,
      // User filters merge under the group scope, which always wins so it can't be overridden.
      filter: {
        ...dataViewState.apiFilter.filter,
        ...(dataViewState.searchBar.state && { name: { $like: dataViewState.searchBar.state } }),
        experiment_group_id: experimentGroupId,
      } as ExperimentFilter,
    },
    { query: { placeholderData: keepPreviousData, enabled: !!experimentGroupId } }
  );

  const experimentsData = experimentsResponse?.data;
  const totalCount = experimentsResponse?.pagination?.total_results ?? experimentsData?.length ?? 0;

  const tableData = useMemo<ExperimentRow[]>(
    () =>
      (experimentsData ?? []).map((experiment) => ({
        ...experiment,
        id: experiment.id ?? experiment.name ?? '',
      })),
    [experimentsData]
  );

  const makeColumns = useCallback<
    ComponentProps<typeof DataViewRoot<ExperimentRow>>['makeColumns']
  >(
    ({ accessor }) => [
      accessor('name', {
        header: 'Name',
        enableSorting: true,
        enableHiding: false,
        size: 300,
        cell: ({ row }) => {
          const { name, summary } = row.original;
          if (!summary) return <Text>{name}</Text>;
          return (
            <Tooltip slotContent={summary} className={tooltipClassName} side="bottom">
              <Text className="cursor-default border-b border-dotted border-brand">{name}</Text>
            </Tooltip>
          );
        },
      }),
      accessor('agent_name', {
        header: 'Agent Name',
        enableSorting: false,
        meta: {
          filter: { type: 'text', label: 'Agent Name', placeholder: 'Filter by Agent Name' },
        },
        cell: ({ row }) => <Text>{row.original.agent_name || '-'}</Text>,
      }),
      accessor('agent_version', {
        header: 'Agent Version',
        enableSorting: false,
        meta: {
          filter: { type: 'text', label: 'Agent Version', placeholder: 'Filter by Agent Version' },
        },
        cell: ({ row }) => <Text>{row.original.agent_version || '-'}</Text>,
      }),
      accessor('dataset_name', {
        header: 'Dataset Name',
        enableSorting: false,
        meta: {
          filter: { type: 'text', label: 'Dataset Name', placeholder: 'Filter by Dataset Name' },
        },
        cell: ({ row }) => <Text>{row.original.dataset_name || '-'}</Text>,
      }),
      accessor('dataset_version', {
        header: 'Dataset Version',
        enableSorting: false,
        meta: {
          filter: {
            type: 'text',
            label: 'Dataset Version',
            placeholder: 'Filter by Dataset Version',
          },
        },
        cell: ({ row }) => <Text>{row.original.dataset_version || '-'}</Text>,
      }),
      accessor((original) => original.model_names?.join(', '), {
        id: 'model_names',
        header: 'Model Names',
        enableSorting: false,
        cell: ({ getValue }) => <Text>{getValue<string>() || '-'}</Text>,
      }),
      accessor((original) => formatScores(original.aggregate_scores), {
        id: 'aggregate_scores',
        header: 'Aggregate Scores',
        enableSorting: false,
      }),
      accessor((original) => original.cost_usd?.mean, {
        id: 'cost_usd',
        header: 'Avg Cost',
        enableSorting: false,
        cell: ({ row }) => {
          const mean = row.original.cost_usd?.mean;
          return <Text>{mean != null ? `$${mean.toFixed(3)}` : '-'}</Text>;
        },
      }),
      accessor((original) => original.latency_ms?.mean, {
        id: 'latency_ms',
        header: 'Avg Latency',
        enableSorting: false,
        cell: ({ row }) => {
          const mean = row.original.latency_ms?.mean;
          return <Text>{mean != null ? `${Math.round(mean)} ms` : '-'}</Text>;
        },
      }),
      accessor((original) => original.run_count, {
        id: 'run_count',
        header: 'Run Count',
        enableSorting: false,
        cell: ({ row }) => <Text>{String(row.original.run_count ?? 0)}</Text>,
      }),
      accessor('created_at', {
        header: 'Created',
        size: 200,
        enableSorting: true,
        meta: { filter: dateTimeFilter('Created At') },
        cell: ({ row }) =>
          row.original.created_at ? (
            <RelativeTime datetime={row.original.created_at} />
          ) : (
            <Text>-</Text>
          ),
      }),
      // Filter-only columns (hidden via columnVisibility above).
      accessor(() => '', {
        id: 'created_by',
        header: 'Created By',
        enableSorting: false,
        enableHiding: false,
        meta: {
          filter: { type: 'text', label: 'Created By', placeholder: 'Filter by Created By' },
        },
      }),
    ],
    []
  );

  if (groupError) {
    return <ErrorMessage message="Failed to load experiment group." />;
  }

  if (error) {
    return <ErrorMessage message="Failed to load experiments." />;
  }

  return (
    <StudioDataView
      dataViewState={dataViewState}
      makeColumns={makeColumns}
      searchField="name"
      onRowClick={(row) =>
        navigate(getExperimentDetailRoute(workspace, experimentGroupName, row.name))
      }
      toolbarSlotEnd={
        <EditColumnsMenu
          kind="secondary"
          showChevron={false}
          // EditColumnsMenu exposes no width control for its dropdown, so this zero-height
          // spacer sets a min width on the menu (which sizes to its widest child).
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
          data: tableData,
          totalCount,
          requestStatus: isGroupLoading || (isLoading && !experimentsData) ? 'loading' : undefined,
        },
        DataViewTableContent: {
          renderEmptyState: () => (
            <TableEmptyState
              header="No Experiments"
              emptyMessage="This group has no experiments yet."
            />
          ),
        },
      }}
    />
  );
};
