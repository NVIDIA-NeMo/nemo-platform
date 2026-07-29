// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ROW_ACTIONS_COLUMN_SIZE,
  StudioDataView,
} from '@nemo/common/src/components/DataView/StudioDataView';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { Flex, PageHeader, Stack, Tag, Text } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { type InsightListItem, useOptimizerListInsights } from '@studio/api/optimizer';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { ErrorPanel } from '@studio/components/ErrorPanel';
import { FeatureFlagBadge } from '@studio/components/FeatureFlagBadge';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { insightStatusColor } from '@studio/routes/optimizer/insightStatus';
import { getOptimizerInsightRoute, getOptimizerRoute } from '@studio/routes/utils';
import { keepPreviousData } from '@tanstack/react-query';
import { Lightbulb } from 'lucide-react';
import { type ComponentProps, type FC } from 'react';
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

  const makeColumns: ComponentProps<typeof StudioDataView<InsightListItem>>['makeColumns'] = (
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
    accessor('experiment_group_count', {
      header: 'Experiments',
      enableSorting: false,
      size: 110,
      cell({ row }) {
        return <Text>{row.original.experiment_group_count ?? '—'}</Text>;
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
    accessor('last_seen_at', {
      header: 'Last Seen',
      enableSorting: false,
      size: 140,
      cell({ row }) {
        return row.original.last_seen_at ? (
          <RelativeTime datetime={row.original.last_seen_at} />
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
          slotDescription="Leverage the optimizer agent to review your code and traces and suggest insights."
        />
        <StudioDataView
          dataViewState={dataViewState}
          makeColumns={makeColumns}
          onRowClick={(row) => navigate(getOptimizerInsightRoute(workspace, row.id))}
          attributes={{
            DataViewRoot: {
              data: data?.data ?? [],
              totalCount: data?.pagination?.total_results,
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
