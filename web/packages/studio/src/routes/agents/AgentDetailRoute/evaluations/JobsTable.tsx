// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { PlatformJobTerminalStatuses } from '@nemo/common/src/constants/query';
import { useLiveSeconds } from '@nemo/common/src/hooks/useLiveSeconds';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { formatDurationMs, formatTimeInSeconds, utcToLocalDate } from '@nemo/common/src/utils/date';
import { Text } from '@nvidia/foundations-react-core';
import {
  EVAL_JOB_KIND_LABEL,
  type EvalJobRow,
  evalDurationMs,
  evalJobDetailRoute,
} from '@studio/api/evaluation/utils';
import type { AgentEvaluationRow } from '@studio/routes/agents/AgentDetailRoute/useAgentDetails';
import { getEvaluationDetailRoute } from '@studio/routes/utils';
import { ListChecks } from 'lucide-react';
import { type ComponentProps, type FC, useCallback } from 'react';
import { useNavigate } from 'react-router';

/** Elapsed time for one job row: a live counter while it runs, the published run's recorded
 *  duration once it finished, and an em dash for a job that ended without publishing.
 *
 *  A completed job's own `updated_at` is not an end time — the job row is written at create and on
 *  rerun only, never on a status transition — so the duration has to come from the evaluation. */
const DurationCell: FC<{ row: EvalJobRow; durationMs?: number }> = ({ row, durationMs }) => {
  const isTerminal = PlatformJobTerminalStatuses.some((status) => status === row.status);
  // `enabled` is what actually stops the timer: the hook's interval effect keys off its *locked*
  // start date, so clearing `startDate` alone leaves a row that finished mid-poll ticking (and
  // re-rendering the table) once a second forever.
  const liveSeconds = useLiveSeconds({
    startDate: isTerminal ? undefined : utcToLocalDate(row.created_at),
    enabled: !isTerminal,
  });
  if (!isTerminal) return <Text>{formatTimeInSeconds(liveSeconds)}</Text>;
  return <Text>{formatDurationMs(durationMs)}</Text>;
};

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

  const durationMsFor = useCallback(
    (row: EvalJobRow): number | undefined => {
      const published = row.evaluationName
        ? evaluations.find((evaluation) => evaluation.name === row.evaluationName)
        : undefined;
      return evalDurationMs(published?.metadata);
    },
    [evaluations]
  );

  const makeColumns: ComponentProps<typeof StudioDataView<EvalJobRow>>['makeColumns'] = useCallback(
    ({ accessor }, { rowActionsColumn }) => [
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
      // A just-finished run stays on '—' here for up to a minute: the evaluations it reads are
      // filtered by `agent_name`, which Intake denormalizes on an interval after publish.
      accessor(durationMsFor, {
        id: 'duration',
        header: 'Duration',
        enableSorting: false,
        cell: ({ row, getValue }) => (
          <DurationCell row={row.original} durationMs={getValue<number | undefined>()} />
        ),
      }),
      rowActionsColumn({
        rowActions: (row) => [
          {
            children: 'View job',
            onSelect: () => navigate(evalJobDetailRoute(workspace, row)),
          },
        ],
      }),
    ],
    [durationMsFor, navigate, workspace]
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
