// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Root as DataViewRoot } from '@nemo/common/src/components/DataView/internal';
import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { useGetExperiment, useListExperimentSessions } from '@nemo/sdk/generated/platform/api';
import type { ExperimentSessionResponse } from '@nemo/sdk/generated/platform/schema';
import { Text, Tooltip } from '@nvidia/foundations-react-core';
import { Empty } from '@studio/components/dataViews/ExperimentSessionsDataView/Empty';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { tooltipClassName } from '@studio/styles/common';
import { keepPreviousData } from '@tanstack/react-query';
import { type ComponentProps, type FC, useMemo } from 'react';

type SessionRow = ExperimentSessionResponse & { _rowId: string };

interface ExperimentSessionsDataViewProps {
  experimentName: string;
  experimentGroupName: string;
}

const mapStatusForBadge = (status: ExperimentSessionResponse['status']) =>
  status === 'success' ? 'completed' : status;

const formatEvaluatorScores = (scores: ExperimentSessionResponse['evaluator_scores']): string => {
  if (!scores || Object.keys(scores).length === 0) return '-';
  return Object.entries(scores)
    .map(([name, value]) => `${name}: ${(value * 100).toFixed(1)}%`)
    .join(', ');
};

export const ExperimentSessionsDataView: FC<ExperimentSessionsDataViewProps> = ({
  experimentName,
  experimentGroupName,
}) => {
  const workspace = useWorkspaceFromPath();
  const dataViewState = useStudioDataViewState({});
  const { data: experiment } = useGetExperiment(workspace, experimentName);

  const page = dataViewState.pagination.state.pageIndex + 1;
  const pageSize = dataViewState.pagination.state.pageSize;

  const { data: sessionsResponse, isLoading } = useListExperimentSessions(
    workspace,
    experimentName,
    { page, page_size: pageSize },
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
    accessor((original) => formatEvaluatorScores(original.evaluator_scores), {
      id: 'evaluator_scores',
      header: 'Evaluator scores',
      enableSorting: false,
      cell: ({ row }) => {
        const formatted = formatEvaluatorScores(row.original.evaluator_scores);
        if (formatted === '-') return <Text>-</Text>;
        return (
          <Tooltip slotContent={formatted} className={tooltipClassName} side="bottom">
            <Text className="cursor-default truncate max-w-[200px] block">{formatted}</Text>
          </Tooltip>
        );
      },
    }),
  ];

  return (
    <StudioDataView
      dataViewState={dataViewState}
      makeColumns={makeColumns}
      attributes={{
        DataViewRoot: {
          data: tableData,
          totalCount,
          requestStatus: isLoading && !sessionsData ? 'loading' : undefined,
        },
        DataViewTableContent: {
          renderEmptyState: () => (
            <Empty
              experimentGroupName={experimentGroupName}
              datasetName={experiment?.dataset_name ?? '<dataset>'}
            />
          ),
        },
      }}
    />
  );
};
