// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import * as DataView from '@nemo/common/src/components/DataView/internal';
import { useRowClick } from '@nemo/common/src/components/DataView/useRowClick';
import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { DEFAULT_PAGE_SIZE_OPTIONS } from '@nemo/common/src/constants/pagination';
import { useListExperimentGroups } from '@nemo/sdk/generated/platform/api';
import type { ExperimentGroupResponse } from '@nemo/sdk/generated/platform/schema';
import { Button, Text } from '@nvidia/foundations-react-core';
import { getExperimentGroupDetailRoute } from '@studio/routes/utils';
import { keepPreviousData } from '@tanstack/react-query';
import { FlaskConical } from 'lucide-react';
import { type ComponentProps, type FC } from 'react';
import { useNavigate } from 'react-router-dom';

const makeColumns: ComponentProps<typeof DataView.Root<ExperimentGroupResponse>>['makeColumns'] = ({
  accessor,
}) => [
  accessor('name', {
    header: 'Experiments',
    enableSorting: false,
    size: 280,
    cell: ({ getValue }) => <Text>{getValue()}</Text>,
  }),
  accessor('evaluation_count', {
    header: 'Evaluations',
    enableSorting: false,
    size: 100,
    cell: ({ getValue }) => <Text>{getValue() ?? 0}</Text>,
  }),
  accessor('updated_at', {
    header: 'Updated',
    enableSorting: false,
    size: 120,
    cell: ({ row }) =>
      row.original.updated_at ? (
        <RelativeTime datetime={row.original.updated_at} />
      ) : (
        <Text>—</Text>
      ),
  }),
];

interface InsightExperimentGroupsProps {
  workspace: string;
  insightId: string;
  onRunExperiment: () => void;
  runExperimentDisabled: boolean;
}

export const InsightExperimentGroups: FC<InsightExperimentGroupsProps> = ({
  workspace,
  insightId,
  onRunExperiment,
  runExperimentDisabled,
}) => {
  const navigate = useNavigate();
  const dataViewState = DataView.useDataViewState({
    pagination: { paginationOptions: DEFAULT_PAGE_SIZE_OPTIONS },
  });
  const { pageIndex, pageSize } = dataViewState.pagination.state;
  const {
    data: response,
    isError,
    isFetching,
    refetch,
  } = useListExperimentGroups(
    workspace,
    {
      page: pageIndex + 1,
      page_size: pageSize,
      sort: '-created_at',
      filter: { insight_id: insightId },
    },
    { query: { placeholderData: keepPreviousData } }
  );
  const groups = response?.data ?? [];
  const { wrapColumns, onClick, className } = useRowClick(
    (group: ExperimentGroupResponse) =>
      navigate(getExperimentGroupDetailRoute(workspace, group.name)),
    groups
  );

  return (
    <DataView.Root
      className="min-h-[160px]"
      dataMode="manual"
      state={dataViewState}
      data={groups}
      totalCount={response?.pagination?.total_results ?? 0}
      requestStatus={isError ? 'error' : isFetching ? 'loading' : undefined}
      loadingRows={pageSize}
      makeColumns={wrapColumns(makeColumns)}
    >
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <DataView.TableContent
          className={`min-h-0 flex-1 overflow-auto bg-transparent [&_td]:!bg-transparent [&_thead]:!bg-transparent [&_thead_th]:!bg-transparent ${className}`}
          onClick={onClick}
          renderEmptyState={() => (
            <TableEmptyState
              header="No experiments"
              emptyMessage="No experiments for this insight."
              icon={<FlaskConical className="size-12" />}
              actions={
                <Button
                  kind="primary"
                  color="brand"
                  disabled={runExperimentDisabled}
                  onClick={onRunExperiment}
                >
                  Run experiment
                </Button>
              }
            />
          )}
          renderErrorState={() => (
            <ErrorMessage
              header="Failed to load experiments"
              message="The experiments for this insight could not be loaded."
              slotFooter={
                <Button type="button" kind="tertiary" onClick={() => void refetch()}>
                  Retry
                </Button>
              }
            />
          )}
        />
        <DataView.Pagination
          className="px-density-md py-density-sm"
          showItemsPerPage
          pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
        />
      </div>
    </DataView.Root>
  );
};
