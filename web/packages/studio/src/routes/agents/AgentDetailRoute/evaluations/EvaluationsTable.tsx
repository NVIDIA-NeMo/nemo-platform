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
import { BulkDeleteModal } from '@studio/components/BulkDeleteModal';
import {
  evaluatorScores,
  formatCost,
  formatLatency,
} from '@studio/routes/agents/AgentDetailRoute/evaluations/formatRollups';
import type { AgentEvaluationRow } from '@studio/routes/agents/AgentDetailRoute/useAgentDetails';
import { getEvaluationDetailRoute } from '@studio/routes/utils';
import { useQueryClient } from '@tanstack/react-query';
import { FlaskConical, Trash } from 'lucide-react';
import { type ComponentProps, type FC, useCallback, useState } from 'react';
import { useNavigate } from 'react-router';

interface EvaluationsTableProps {
  workspace: string;
  evaluations: AgentEvaluationRow[];
}

/** Every published evaluation for the agent, ungrouped. */
export const EvaluationsTable: FC<EvaluationsTableProps> = ({ workspace, evaluations }) => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const dataViewState = useStudioDataViewState();
  const [deleteRows, setDeleteRows] = useState<AgentEvaluationRow[]>([]);

  // Soft-deletes on the server: the row leaves this list (which filters is_deleted out) but the
  // spans, the evaluator job, and the Experiment it belonged to are all untouched.
  const handleDelete = useCallback(
    async (rows: AgentEvaluationRow[]) => {
      await Promise.all(rows.map((row) => deleteEvaluation(workspace, row.name)));
      await queryClient.invalidateQueries({ queryKey: getListEvaluationsQueryKey(workspace) });
    },
    [workspace, queryClient]
  );

  const makeColumns: ComponentProps<typeof StudioDataView<AgentEvaluationRow>>['makeColumns'] =
    useCallback(
      ({ accessor }, { rowSelectionColumn }) => [
        rowSelectionColumn({ size: ROW_SELECTION_COLUMN_SIZE }),
        // Explicit sizes throughout: without them every column falls back to defaultColumn's
        // min/max and the table sizes to content, so the Scores chips steal width and the name
        // wraps. Sizes are relative weights the table distributes across the container.
        accessor('name', {
          header: 'Evaluation',
          size: 240,
          cell: ({ row }) => <Text title={row.original.name}>{row.original.name}</Text>,
        }),
        accessor('run_count', {
          header: 'Runs',
          size: 90,
          cell: ({ row }) => <Text>{row.original.run_count ?? 0}</Text>,
        }),
        accessor('test_case_count', {
          header: 'Test cases',
          size: 110,
          cell: ({ row }) => <Text>{row.original.test_case_count ?? 0}</Text>,
        }),
        accessor('aggregate_scores', {
          header: 'Scores',
          size: 300,
          enableSorting: false,
          cell: ({ row }) => {
            const scores = evaluatorScores(row.original);
            if (scores.length === 0) return <Text>—</Text>;
            // One chip per evaluator, wrapping rather than truncating into an unreadable run-on.
            return (
              <Flex gap="density-xs" className="flex-wrap">
                {scores.map((score) => (
                  <Flex
                    key={score.label}
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
          size: 120,
          enableSorting: false,
          cell: ({ row }) => <Text>{formatLatency(row.original.latency_ms?.mean)}</Text>,
        }),
        accessor('cost_usd', {
          header: 'Cost',
          size: 100,
          enableSorting: false,
          cell: ({ row }) => <Text>{formatCost(row.original.cost_usd?.sum)}</Text>,
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
    <>
      <StudioDataView<AgentEvaluationRow>
        dataViewState={dataViewState}
        makeColumns={makeColumns}
        // The detail route nests under an experiment; a row without one has nowhere to go.
        onRowClick={(row) =>
          row.experimentName &&
          navigate(getEvaluationDetailRoute(workspace, row.experimentName, row.name))
        }
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
