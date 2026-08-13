// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { Text } from '@nvidia/foundations-react-core';
import type { AgentExperimentRow } from '@studio/routes/agents/AgentDetailRoute/evaluations/groupByExperiment';
import { getExperimentDetailRoute } from '@studio/routes/utils';
import { FolderTree } from 'lucide-react';
import { type ComponentProps, type FC, useCallback } from 'react';
import { useNavigate } from 'react-router';

interface ExperimentsTableProps {
  workspace: string;
  experiments: AgentExperimentRow[];
}

/** The agent's evaluations rolled up by the experiment they belong to. Selecting one opens the
 *  experiment's own route, which already lists the evaluations under it. */
export const ExperimentsTable: FC<ExperimentsTableProps> = ({ workspace, experiments }) => {
  const navigate = useNavigate();
  const dataViewState = useStudioDataViewState();

  const makeColumns: ComponentProps<typeof StudioDataView<AgentExperimentRow>>['makeColumns'] =
    useCallback(
      // Explicit sizes, matching the sibling tables, so the three views line up rather than each
      // sizing to its own content.
      ({ accessor }) => [
        accessor('name', {
          header: 'Experiment',
          size: 240,
          cell: ({ row }) => <Text title={row.original.name}>{row.original.name}</Text>,
        }),
        accessor('evaluationCount', {
          header: 'Evaluations',
          size: 130,
          cell: ({ row }) => <Text>{row.original.evaluationCount}</Text>,
        }),
        accessor('runCount', {
          header: 'Runs',
          size: 90,
          cell: ({ row }) => <Text>{row.original.runCount}</Text>,
        }),
        accessor('latestCreatedAt', {
          header: 'Latest run',
          size: 140,
          cell: ({ row }) =>
            row.original.latestCreatedAt ? (
              <RelativeTime datetime={row.original.latestCreatedAt} />
            ) : (
              '—'
            ),
        }),
      ],
      []
    );

  return (
    <StudioDataView<AgentExperimentRow>
      dataViewState={dataViewState}
      makeColumns={makeColumns}
      onRowClick={(row) => navigate(getExperimentDetailRoute(workspace, row.name))}
      attributes={{
        DataViewRoot: { data: experiments },
        DataViewTableContent: {
          renderEmptyState: () => (
            <TableEmptyState
              icon={<FolderTree className="size-16" />}
              header="No experiments yet"
              emptyMessage="An experiment appears here once one of its evaluations publishes results for this agent."
            />
          ),
        },
      }}
    />
  );
};
