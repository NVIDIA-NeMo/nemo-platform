// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { Text } from '@nvidia/foundations-react-core';
import {
  EVAL_JOB_KIND_LABEL,
  type EvalJobRow,
  evalJobDetailRoute,
} from '@studio/api/evaluation/utils';
import type { AgentEvaluationRow } from '@studio/routes/agents/AgentDetailRoute/useAgentDetails';
import { getEvaluationDetailRoute } from '@studio/routes/utils';
import { ListChecks } from 'lucide-react';
import { type ComponentProps, type FC, useCallback } from 'react';
import { useNavigate } from 'react-router';

interface JobsTableProps {
  workspace: string;
  jobs: EvalJobRow[];
  /** Published evaluations, used to resolve a completed job's results destination. */
  evaluations: AgentEvaluationRow[];
}

/** Evaluator jobs for the agent, visible from the moment they are submitted.
 *
 *  This view exists because Intake cannot answer "this agent's runs" until a run publishes: its
 *  ``agent_name`` facet is denormalized from ingested spans, so a new evaluation is invisible
 *  there for the whole run plus the denormalizer interval. A job is queryable immediately. */
export const JobsTable: FC<JobsTableProps> = ({ workspace, jobs, evaluations }) => {
  const navigate = useNavigate();
  const dataViewState = useStudioDataViewState();

  const destinationFor = useCallback(
    (row: EvalJobRow): string => {
      const published = row.evaluationName
        ? evaluations.find((evaluation) => evaluation.name === row.evaluationName)
        : undefined;
      return published?.experimentName
        ? getEvaluationDetailRoute(workspace, published.experimentName, published.name)
        : evalJobDetailRoute(workspace, row);
    },
    [workspace, evaluations]
  );

  const makeColumns: ComponentProps<typeof StudioDataView<EvalJobRow>>['makeColumns'] = useCallback(
    ({ accessor }) => [
      accessor('name', {
        header: 'Job',
        cell: ({ row }) => <Text title={row.original.name}>{row.original.name}</Text>,
      }),
      accessor('kind', {
        header: 'Kind',
        cell: ({ row }) => <Text>{EVAL_JOB_KIND_LABEL[row.original.kind]}</Text>,
      }),
      accessor('status', {
        header: 'Status',
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
      }),
      accessor('evaluationName', {
        header: 'Evaluation',
        cell: ({ row }) => (
          <Text title={row.original.evaluationName ?? undefined} color="secondary">
            {row.original.evaluationName ?? '—'}
          </Text>
        ),
      }),
      accessor('created_at', {
        header: 'Created',
        cell: ({ row }) =>
          row.original.created_at ? <RelativeTime datetime={row.original.created_at} /> : '—',
      }),
    ],
    []
  );

  return (
    <StudioDataView<EvalJobRow>
      dataViewState={dataViewState}
      makeColumns={makeColumns}
      onRowClick={(row) => navigate(destinationFor(row))}
      attributes={{
        DataViewRoot: { data: jobs },
        DataViewTableContent: {
          renderEmptyState: () => (
            <TableEmptyState
              icon={<ListChecks className="size-16" />}
              header="No evaluation jobs yet"
              emptyMessage="Runs appear here as soon as they are submitted, before any results are published."
            />
          ),
        },
      }}
    />
  );
};
