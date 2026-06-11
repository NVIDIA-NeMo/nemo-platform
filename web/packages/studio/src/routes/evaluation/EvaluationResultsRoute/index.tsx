// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { ScrollTable } from '@nemo/common/src/components/ScrollTable';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { TableHeaderButton } from '@nemo/common/src/components/TableHeaderButton';
import { JOB_POLLING_INTERVAL_MS } from '@nemo/common/src/constants';
import { useTableFilters } from '@nemo/common/src/hooks/useTableFilters';
import { getAriaSort } from '@nemo/common/src/utils/a11y';
import { tablePaginationSort } from '@nemo/common/src/utils/tablePaginationSort';
import { useEvaluatorListEvaluateJobs } from '@nemo/sdk/generated/evaluator/api';
import { Button, Stack, TableRowDefinition } from '@nvidia/foundations-react-core';
import { DocumentationButton } from '@studio/components/DocumentationButton';
import { LINK_DOCS_STUDIO_EVALUATION } from '@studio/constants/links';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getEvaluationResultDetailsRoute } from '@studio/routes/utils';
import { keepPreviousData } from '@tanstack/react-query';
import { ArrowDown, ArrowUp } from 'lucide-react';
import { useMemo, type FC } from 'react';
import { Link } from 'react-router-dom';

export const EvaluationResultsRoute: FC = () => {
  const workspace = useWorkspaceFromPath();

  const { filterState, handleSort, handlePaginationChange } = useTableFilters({});

  const {
    data: jobsData,
    isLoading,
    refetch,
    error,
  } = useEvaluatorListEvaluateJobs(
    workspace,
    {
      ...tablePaginationSort(filterState),
    },
    {
      query: {
        placeholderData: keepPreviousData,
        refetchOnMount: 'always',
        refetchInterval: JOB_POLLING_INTERVAL_MS,
      },
    }
  );

  const jobs = useMemo(() => jobsData?.data || [], [jobsData?.data]);

  const paginationProps = useMemo(
    () => ({
      page: filterState.page,
      pageSize: filterState.page_size,
      totalItems: jobsData?.pagination?.total_results ?? 0,
      onPageChange: (page: number) => handlePaginationChange({ page }),
      onPageSizeChange: (pageSize: number) => handlePaginationChange({ pageSize }),
    }),
    [
      filterState.page,
      filterState.page_size,
      jobsData?.pagination?.total_results,
      handlePaginationChange,
    ]
  );

  const columns = useMemo(
    () => [
      {
        children: 'Name',
      },
      {
        children: 'Status',
      },
      {
        children: (
          <TableHeaderButton onClick={() => handleSort('created_at')}>
            Created
            {filterState.sort_by === 'created_at' &&
              (filterState.order === 'asc' ? <ArrowUp /> : <ArrowDown />)}
          </TableHeaderButton>
        ),
        attributes: {
          TableHeaderCell: {
            scope: 'col',
            'aria-sort': filterState.sort_by
              ? getAriaSort(filterState.sort_by, 'created_at', filterState.order || 'desc')
              : 'descending',
          },
        },
      },
    ],
    [filterState, handleSort]
  );

  const rows = useMemo<TableRowDefinition[]>(
    () =>
      jobs.map((job) => {
        const name = job.name ?? '';
        const createdAt = job.created_at;

        return {
          id: job.id ?? name,
          cells: [
            {
              children: name ? (
                <Link
                  to={getEvaluationResultDetailsRoute(workspace, name)}
                  className="text-content-link hover:underline"
                >
                  {name}
                </Link>
              ) : (
                '-'
              ),
            },
            {
              children: <StatusBadge status={job.status} />,
            },
            {
              children: createdAt ? <RelativeTime datetime={createdAt} /> : '-',
            },
          ],
        };
      }),
    [jobs, workspace]
  );

  if (error) {
    return (
      <ErrorMessage
        message="Failed to fetch evaluations"
        slotFooter={
          <Button type="button" kind="tertiary" onClick={() => refetch()}>
            Retry
          </Button>
        }
      />
    );
  }

  return (
    <ScrollTable
      columns={columns}
      rows={rows}
      paginationProps={paginationProps}
      loading={isLoading && rows.length === 0}
      pagination
      slotEmptyState={
        <TableEmptyState
          header="Manage Evaluations"
          emptyMessage="Refine and optimize your large language models (LLMs) for enhanced performance and real-world applicability."
          actions={
            <Stack direction="row" gap="density-md">
              <DocumentationButton href={LINK_DOCS_STUDIO_EVALUATION} />
            </Stack>
          }
        />
      }
    />
  );
};
