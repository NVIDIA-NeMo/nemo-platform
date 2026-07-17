// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ROW_ACTIONS_COLUMN_SIZE,
  StudioDataView,
} from '@nemo/common/src/components/DataView/StudioDataView';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { useListExperimentGroups } from '@nemo/sdk/generated/platform/api';
import { Flex, PageHeader, Stack, Tag, Text } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { type Insight, useOptimizerListInsights } from '@studio/api/optimizer';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { ErrorPanel } from '@studio/components/ErrorPanel';
import { FeatureFlagBadge } from '@studio/components/FeatureFlagBadge';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { insightStatusColor } from '@studio/routes/optimizer/insightStatus';
import { getOptimizerInsightRoute, getOptimizerRoute } from '@studio/routes/utils';
import { keepPreviousData } from '@tanstack/react-query';
import { Lightbulb } from 'lucide-react';
import { type ComponentProps, type FC, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';

export const OptimizerRoute: FC = () => {
  const workspace = useWorkspaceFromPath();

  useBreadcrumbs({
    items: [{ href: getOptimizerRoute(workspace), slotLabel: 'Insights' }],
  });

  const navigate = useNavigate();

  const dataViewState = useStudioDataViewState({
    defaultSort: [{ id: 'created_at', desc: true }],
  });

  const sortState = dataViewState.sorting.state[0];
  const sortParam = sortState ? `${sortState.desc ? '-' : ''}${sortState.id}` : '-created_at';

  const { data, isFetching, error } = useOptimizerListInsights(
    workspace,
    {
      page: dataViewState.pagination.state.pageIndex + 1,
      page_size: dataViewState.pagination.state.pageSize,
      sort: sortParam,
    },
    { query: { placeholderData: keepPreviousData } }
  );

  const pagination = data?.pagination;

  // Per-insight experiment count: an experiment group carries `insight_id`, so we map each insight
  // to the total experiments across its group(s). Mirrors the insight detail page's linkage.
  // NOTE: bounded to the first 100 groups (no server-side insight_id filter yet).
  const { data: groupsData } = useListExperimentGroups(workspace, { page_size: 100 });
  const experimentCountByInsight = useMemo(() => {
    const counts = new Map<string, number>();
    for (const group of groupsData?.data ?? []) {
      if (!group.insight_id) continue;
      counts.set(
        group.insight_id,
        (counts.get(group.insight_id) ?? 0) + (group.experiment_count ?? 0)
      );
    }
    return counts;
  }, [groupsData]);

  const makeColumns: ComponentProps<typeof StudioDataView<Insight>>['makeColumns'] = (
    { accessor },
    { rowActionsColumn }
  ) => [
    accessor('status', {
      header: 'Status',
      enableSorting: false,
      size: 110,
      cell({ row }) {
        const status = row.original.status;
        return (
          <Tag kind="outline" color={insightStatusColor(status)} readOnly>
            {status}
          </Tag>
        );
      },
    }),
    accessor('title', {
      header: 'Insight',
      enableSorting: false,
      size: 240,
      cell({ row }) {
        return <Text className="font-bold">{row.original.title}</Text>;
      },
    }),
    accessor('agent', {
      header: 'Agent',
      enableSorting: false,
      size: 160,
      cell({ row }) {
        return <Text className="truncate">{row.original.agent || '—'}</Text>;
      },
    }),
    accessor('trace_refs', {
      id: 'traces',
      header: 'Traces',
      enableSorting: false,
      size: 80,
      cell({ row }) {
        return <Text>{row.original.trace_refs?.length ?? 0}</Text>;
      },
    }),
    accessor('id', {
      id: 'experiments',
      header: 'Experiments',
      enableSorting: false,
      size: 110,
      cell({ row }) {
        return <Text>{experimentCountByInsight.get(row.original.id) ?? 0}</Text>;
      },
    }),
    accessor('created_at', {
      header: 'Created',
      enableSorting: true,
      size: 140,
      cell({ row }) {
        return row.original.created_at ? (
          <RelativeTime datetime={row.original.created_at} />
        ) : (
          <Text>—</Text>
        );
      },
    }),
    accessor('updated_at', {
      header: 'Updated',
      enableSorting: true,
      size: 140,
      cell({ row }) {
        return row.original.updated_at ? (
          <RelativeTime datetime={row.original.updated_at} />
        ) : (
          <Text>—</Text>
        );
      },
    }),
    rowActionsColumn({
      size: ROW_ACTIONS_COLUMN_SIZE,
      enableResizing: false,
      rowActions: () => [],
    }),
  ];

  return (
    <AccessibleTitle title="Insights">
      <Stack className="h-full overflow-auto" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading={
            <Flex className="items-center gap-density-md">
              Insights
              <FeatureFlagBadge flag="optimizerEnabled" />
            </Flex>
          }
          slotDescription="Leverage the optimizer agent to review your code and traces and suggest insights. Learn more."
        />
        <StudioDataView
          dataViewState={dataViewState}
          makeColumns={makeColumns}
          onRowClick={(row: Insight) => navigate(getOptimizerInsightRoute(workspace, row.id))}
          attributes={{
            DataViewRoot: {
              data: data?.data ?? [],
              totalCount: pagination?.total_results,
              requestStatus: error ? 'error' : isFetching ? 'loading' : undefined,
            },
            DataViewTableContent: {
              renderEmptyState: () => (
                <TableEmptyState
                  icon={<Lightbulb className="h-[64px] w-[64px]" />}
                  header="No insights yet"
                  emptyMessage="Run an optimizer analysis on an agent to surface insights here."
                />
              ),
              renderErrorState: () => (
                <ErrorPanel
                  errorMessage={getErrorMessage(error ?? new Error('Failed to fetch insights'))}
                />
              ),
            },
          }}
        />
      </Stack>
    </AccessibleTitle>
  );
};
