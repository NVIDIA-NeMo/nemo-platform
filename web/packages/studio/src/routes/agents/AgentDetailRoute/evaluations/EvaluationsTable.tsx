// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ROW_SELECTION_COLUMN_SIZE,
  StudioDataView,
} from '@nemo/common/src/components/DataView/StudioDataView';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { deleteEvaluation, getListEvaluationsQueryKey } from '@nemo/sdk/generated/platform/api';
import { Button, Flex, Text } from '@nvidia/foundations-react-core';
import { type EvalJobRow, evalJobDetailRoute } from '@studio/api/evaluation/utils';
import { BulkDeleteModal } from '@studio/components/BulkDeleteModal';
import {
  evaluatorScores,
  formatCost,
  formatLatency,
} from '@studio/routes/agents/AgentDetailRoute/evaluations/formatRollups';
import {
  type AgentEvaluationRow,
  primaryExperimentName,
} from '@studio/routes/agents/AgentDetailRoute/useAgentDetails';
import { getEvaluationDetailRoute } from '@studio/routes/utils';
import { useQueryClient } from '@tanstack/react-query';
import { FlaskConical, Trash } from 'lucide-react';
import { type ComponentProps, type FC, useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';

interface EvaluationsTableProps {
  workspace: string;
  evaluations: AgentEvaluationRow[];
  /** All evaluator jobs for the agent (any status), used to link a published evaluation back to
   *  the job that produced it. Absent until the reverse join finds a match. */
  jobs: EvalJobRow[];
}

/** Every published evaluation for the agent, ungrouped. */
export const EvaluationsTable: FC<EvaluationsTableProps> = ({ workspace, evaluations, jobs }) => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const dataViewState = useStudioDataViewState();
  const [deleteRows, setDeleteRows] = useState<AgentEvaluationRow[]>([]);
  // Reverse of JobsTable's job -> evaluation link: a completed job carries the evaluation it
  // published to, so index by that name to recover the job from an evaluation row.
  const jobByEvaluation = useMemo(() => {
    const map: Record<string, EvalJobRow> = {};
    for (const job of jobs) if (job.evaluationName) map[job.evaluationName] = job;
    return map;
  }, [jobs]);

  const handleDelete = useCallback(
    async (rows: AgentEvaluationRow[]) => {
      const results = await Promise.allSettled(
        rows.map((row) => deleteEvaluation(workspace, row.name))
      );
      await queryClient.invalidateQueries({ queryKey: getListEvaluationsQueryKey(workspace) });

      const failed = rows.filter((_, index) => results[index]?.status === 'rejected');
      if (failed.length) {
        setDeleteRows(failed);
        throw new Error(
          `${failed.length} of ${rows.length} evaluation${rows.length !== 1 ? 's' : ''} could not be deleted. Retry to attempt only those.`
        );
      }
    },
    [workspace, queryClient]
  );

  const makeColumns: ComponentProps<typeof StudioDataView<AgentEvaluationRow>>['makeColumns'] =
    useCallback(
      ({ accessor }, { rowSelectionColumn, rowActionsColumn }) => [
        rowSelectionColumn({ size: ROW_SELECTION_COLUMN_SIZE }),
        accessor('name', {
          header: 'Evaluation',
          cell: ({ row }) => <Text title={row.original.name}>{row.original.name}</Text>,
        }),
        accessor('run_count', {
          header: 'Runs',
          cell: ({ row }) => <Text>{row.original.run_count ?? 0}</Text>,
        }),
        accessor('test_case_count', {
          header: 'Test cases',
          cell: ({ row }) => <Text>{row.original.test_case_count ?? 0}</Text>,
        }),
        accessor('aggregate_scores', {
          header: 'Scores',
          enableSorting: false,
          cell: ({ row }) => {
            const scores = evaluatorScores(row.original);
            if (scores.length === 0) return <Text>—</Text>;
            return (
              <Flex gap="density-xs" className="flex-wrap">
                {scores.map((score) => (
                  <Flex
                    key={score.key}
                    gap="density-xxs"
                    align="baseline"
                    className="rounded bg-surface-raised px-1.5 py-0.5"
                  >
                    <Text kind="body/regular/sm" color="secondary">
                      {score.label}
                    </Text>
                    <Text kind="body/semibold/sm">{score.value}</Text>
                  </Flex>
                ))}
              </Flex>
            );
          },
        }),
        accessor('latency_ms', {
          header: 'Avg latency',
          enableSorting: false,
          cell: ({ row }) => <Text>{formatLatency(row.original.latency_ms?.mean)}</Text>,
        }),
        accessor('cost_usd', {
          header: 'Cost',
          enableSorting: false,
          cell: ({ row }) => <Text>{formatCost(row.original.cost_usd?.sum)}</Text>,
        }),
        accessor('created_at', {
          header: 'Created',
          cell: ({ row }) =>
            row.original.created_at ? <RelativeTime datetime={row.original.created_at} /> : '—',
        }),
        rowActionsColumn({
          rowActions: (row) => {
            const job = jobByEvaluation[row.name];
            return job
              ? [
                  {
                    children: 'View job',
                    onSelect: () => navigate(evalJobDetailRoute(workspace, job)),
                  },
                ]
              : false;
          },
        }),
      ],
      [jobByEvaluation, navigate, workspace]
    );

  return (
    <>
      <StudioDataView<AgentEvaluationRow>
        dataViewState={dataViewState}
        makeColumns={makeColumns}
        onRowClick={(row) => {
          const experimentName = primaryExperimentName(row);
          if (experimentName) {
            navigate(getEvaluationDetailRoute(workspace, experimentName, row.name));
          }
        }}
        renderBulkActions={({ selectedRows }) => (
          <Button
            kind="tertiary"
            aria-label="Delete selected evaluations"
            onClick={() => setDeleteRows(selectedRows)}
          >
            <Trash /> Delete
          </Button>
        )}
        attributes={{
          DataViewRoot: { data: evaluations },
          DataViewTableContent: {
            renderEmptyState: () => (
              <TableEmptyState
                className="py-density-3xl"
                icon={<FlaskConical className="size-16" />}
                header="No published evaluations yet"
                emptyMessage="Results appear here once a run finishes and its telemetry is ingested."
              />
            ),
          },
        }}
      />

      <BulkDeleteModal
        items={deleteRows}
        open={deleteRows.length > 0}
        onDelete={handleDelete}
        title={(count) => `Delete ${count} Evaluation${count !== 1 ? 's' : ''}`}
        onClose={() => {
          setDeleteRows([]);
          dataViewState.rowSelection.set({});
        }}
      />
    </>
  );
};
