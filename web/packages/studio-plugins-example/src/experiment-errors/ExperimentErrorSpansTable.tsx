// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { useQueryPlugin } from '@nemo/studio-plugins-example/queryPlugin/useQueryPlugin';
import type { ExperimentErrorSpans } from '@nemo/studio-plugins-example/experiment-errors/types';
import { Card, Stack, Table, Text, Tooltip } from '@nvidia/foundations-react-core';
import { tooltipClassName } from '@studio/styles/common';
import { type FC } from 'react';

interface Props {
  workspace: string;
  experimentName: string;
}

/**
 * "Spans with errors" table on the error report page: the individual error spans behind the
 * by-type counts, newest first.
 *
 * Backed by the `experiment-error-spans` query plugin (companion to `experiment-error-summary`),
 * which lists error spans across the whole experiment. Renders nothing while loading, when the
 * query plugin is unavailable, or when the experiment has no error spans.
 */
export const ExperimentErrorSpansTable: FC<Props> = ({ workspace, experimentName }) => {
  const { data: result, isLoading, error } = useQueryPlugin<ExperimentErrorSpans>(
    workspace,
    'experiment-error-spans',
    { experiment_id: experimentName },
  );

  const data = result?.data;
  const spans = data?.spans ?? [];
  if (isLoading || error || spans.length === 0) return null;

  return (
    <Card>
      <Stack gap="density-md" padding="density-xl">
        <Stack gap="density-xs">
          <Text kind="title/sm">Spans with errors</Text>
          <Text kind="body/regular/sm" color="secondary">
            {data?.total ?? spans.length} error span{spans.length === 1 ? '' : 's'}, newest first
          </Text>
        </Stack>
        <Table
          className="bg-transparent w-full"
          layout="fixed"
          align="left"
          columns={[
            { children: 'When', attributes: { TableHeaderCell: { style: { width: '140px' } } } },
            { children: 'Span', attributes: { TableHeaderCell: { style: { width: '200px' } } } },
            {
              children: 'Error type',
              attributes: { TableHeaderCell: { style: { width: '180px' } } },
            },
            { children: 'Message' },
          ]}
          rows={spans.map((span) => ({
            cells: [
              {
                children: span.start_time ? (
                  <RelativeTime datetime={span.start_time} />
                ) : (
                  <Text>-</Text>
                ),
              },
              {
                children: (
                  <Text kind="body/regular/sm" className="truncate">
                    {span.name || '-'}
                  </Text>
                ),
              },
              {
                children: (
                  <Text kind="body/regular/sm" className="truncate">
                    {span.error_type}
                  </Text>
                ),
              },
              {
                children: span.error_message ? (
                  <Tooltip
                    slotContent={span.error_message}
                    className={tooltipClassName}
                    side="bottom"
                  >
                    <Text kind="body/regular/sm" className="cursor-default truncate block">
                      {span.error_message}
                    </Text>
                  </Tooltip>
                ) : (
                  <Text>-</Text>
                ),
              },
            ],
          }))}
        />
      </Stack>
    </Card>
  );
};
