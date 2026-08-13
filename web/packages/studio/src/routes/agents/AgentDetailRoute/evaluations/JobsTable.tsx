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

  // A finished run's results live in Intake; everything else only has its job record. The lookup
  // fails while the evaluation is still unpublished or un-indexed, which correctly falls back.
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
      // Explicit sizes, matching EvaluationsTable, so the three views line up rather than each
      // sizing to its own content.
      accessor('name', {
        header: 'Job',
        size: 240,
        cell: ({ row }) => <Text title={row.original.name}>{row.original.name}</Text>,
      }),
      accessor('kind', {
        header: 'Kind',
        size: 140,
        cell: ({ row }) => <Text>{EVAL_JOB_KIND_LABEL[row.original.kind]}</Text>,
      }),
      accessor('status', {
        header: 'Status',
        size: 130,
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
      }),
      accessor('evaluationName', {
        header: 'Evaluation',
        size: 240,
        // Written into the spec at submit, so it is known for every run that asked to publish —
        // not only finished ones. Blank means the run publishes nowhere.
        cell: ({ row }) => (
          <Text title={row.original.evaluationName ?? undefined} color="secondary">
            {row.original.evaluationName ?? '—'}
          </Text>
        ),
      }),
      accessor('created_at', {
        header: 'Created',
        size: 140,
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
