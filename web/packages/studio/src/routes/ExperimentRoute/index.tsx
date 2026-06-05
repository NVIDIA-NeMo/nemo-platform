// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { useListExperimentGroups, useListExperiments } from '@nemo/sdk/generated/platform/api';
import type { ExperimentGroupResponse } from '@nemo/sdk/generated/platform/schema';
import { PageHeader, Panel, Stack, StatusMessage, Text } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { Loading } from '@studio/components/Layouts/Loading';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { keepPreviousData } from '@tanstack/react-query';
import { CircleAlert } from 'lucide-react';
import { type FC } from 'react';

export const ExperimentRoute: FC = () => {
  useBreadcrumbs({ items: [{ slotLabel: 'Experiments' }] });

  const workspace = useWorkspaceFromPath();

  const { data, isLoading, error } = useListExperimentGroups(
    workspace,
    { page: 1, page_size: 50 },
    { query: { placeholderData: keepPreviousData } }
  );

  if (isLoading) {
    return <Loading description="Loading experiments..." />;
  }

  if (error) {
    return (
      <StatusMessage
        className="mx-auto mt-density-2xl"
        size="medium"
        slotMedia={<CircleAlert width={65} height={65} />}
        slotHeading="Error loading experiments"
        slotSubheading={error.message}
      />
    );
  }

  const groups = data?.data ?? [];

  return (
    <AccessibleTitle title="Experiments">
      <Stack className="h-full overflow-auto" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading="Experiments"
          slotDescription="Result ledger for offline optimization. Review results down to the trace level."
        />
        {groups.length === 0 ? (
          <Text kind="body/regular/md" className="text-secondary">
            No experiment groups yet.
          </Text>
        ) : (
          <Stack gap="density-md">
            {groups.map((group: ExperimentGroupResponse) => (
              <ExperimentGroupCard key={group.id} group={group} workspace={workspace} />
            ))}
          </Stack>
        )}
      </Stack>
    </AccessibleTitle>
  );
};

interface ExperimentGroupCardProps {
  group: ExperimentGroupResponse;
  workspace: string;
}

const ExperimentGroupCard: FC<ExperimentGroupCardProps> = ({ group, workspace }) => {
  const { data: experimentsData } = useListExperiments(workspace, {
    filter: { experiment_group_id: group.id },
    page_size: 100,
  });

  const experiments = experimentsData?.data ?? [];
  const experimentCount = experimentsData?.pagination?.total_results ?? experiments.length;
  const datasetNames = [...new Set(experiments.map((e) => e.dataset_name).filter(Boolean))];
  const agentNames = [...new Set(experiments.map((e) => e.agent_name).filter(Boolean))];

  return (
    <Panel elevation="low">
      <Stack gap="density-sm">
        <Text kind="title/sm">{group.name}</Text>
        {group.description && (
          <Text kind="body/regular/sm" className="text-secondary">
            {group.description}
          </Text>
        )}
        <Stack direction="row" gap="density-xl">
          <Stack gap="density-xxs">
            <Text kind="label/bold/xs" className="text-tertiary uppercase">
              Experiments
            </Text>
            <Text kind="body/regular/sm">{experimentCount}</Text>
          </Stack>
          {agentNames.length > 0 && (
            <Stack gap="density-xxs">
              <Text kind="label/bold/xs" className="text-tertiary uppercase">
                Agent
              </Text>
              <Text kind="body/regular/sm">{agentNames.join(', ')}</Text>
            </Stack>
          )}
          {datasetNames.length > 0 && (
            <Stack gap="density-xxs">
              <Text kind="label/bold/xs" className="text-tertiary uppercase">
                Dataset
              </Text>
              <Text kind="body/regular/sm">{datasetNames.join(', ')}</Text>
            </Stack>
          )}
          {group.updated_at && (
            <Stack gap="density-xxs">
              <Text kind="label/bold/xs" className="text-tertiary uppercase">
                Updated
              </Text>
              <Text kind="body/regular/sm">
                <RelativeTime datetime={group.updated_at} />
              </Text>
            </Stack>
          )}
        </Stack>
      </Stack>
    </Panel>
  );
};
