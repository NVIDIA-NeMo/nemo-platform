// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useQueryPlugin } from '@nemo/studio-plugins-example/queryPlugin/useQueryPlugin';
import type { ExperimentErrorSummary } from '@nemo/studio-plugins-example/experiment-errors/types';
import { Card, Stack, Table, Text } from '@nvidia/foundations-react-core';
import { type FC } from 'react';

interface Props {
  workspace: string;
  experimentName: string;
}

const RIGHT_ALIGN = { TableHeaderCell: { style: { textAlign: 'right' as const } } };
const RIGHT_ALIGN_CELL = { TableDataCell: { style: { textAlign: 'right' as const } } };

/**
 * "Errors by type" table on the error report page: error spans grouped by `error_type` with
 * occurrence counts.
 *
 * Backed by the `experiment-error-summary` query plugin, which aggregates over every session in
 * the experiment (not just a loaded test-case page). Renders nothing while loading, when the
 * query plugin is unavailable, or when the experiment has no error spans.
 */
export const ExperimentErrorSummaryTable: FC<Props> = ({ workspace, experimentName }) => {
  const { data: result, isLoading, error } = useQueryPlugin<ExperimentErrorSummary>(
    workspace,
    'experiment-error-summary',
    { experiment_id: experimentName },
  );

  const data = result?.data;
  const rows = data?.rows ?? [];
  if (isLoading || error || rows.length === 0) return null;

  const totalErrorSpans = data?.total_error_spans ?? 0;

  return (
    <Card>
      <Stack gap="density-md" padding="density-xl">
        <Stack gap="density-xs">
          <Text kind="title/sm">Errors by type</Text>
          <Text kind="body/regular/sm" color="secondary">
            {totalErrorSpans} error span{totalErrorSpans === 1 ? '' : 's'} across this experiment
          </Text>
        </Stack>
        <Table
          className="bg-transparent w-full"
          layout="fixed"
          align="left"
          columns={[
            { children: 'Error type' },
            { children: 'Occurrences', attributes: RIGHT_ALIGN },
          ]}
          rows={rows.map((row) => ({
            cells: [
              {
                children: (
                  <Text kind="body/regular/sm" className="truncate">
                    {row.error_type}
                  </Text>
                ),
              },
              { children: row.count.toLocaleString(), attributes: RIGHT_ALIGN_CELL },
            ],
          }))}
        />
      </Stack>
    </Card>
  );
};
