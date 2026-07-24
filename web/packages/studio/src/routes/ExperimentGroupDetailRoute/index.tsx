// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { useGetExperimentGroup } from '@nemo/sdk/generated/platform/api';
import { Button, Card, Flex, PageHeader, Stack, Text } from '@nvidia/foundations-react-core';
import { useOptimizerGetInsight } from '@studio/api/optimizer';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { ExperimentGroupDataView } from '@studio/components/dataViews/ExperimentGroupDataView';
import { ExperimentGroupEditModal } from '@studio/components/ExperimentGroupEditModal';
import { OriginatingInsightLink } from '@studio/components/OriginatingInsightLink';
import { OPTIMIZER_ENABLED } from '@studio/constants/environment';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { ExperimentGroupMetrics } from '@studio/routes/ExperimentGroupDetailRoute/ExperimentGroupMetrics';
import { getExperimentRoute } from '@studio/routes/utils';
import { useLocalStorage } from '@studio/util/hooks/useLocalStorage';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { ChartScatter, Pencil } from 'lucide-react';
import { type FC, useState } from 'react';

export const ExperimentGroupDetailRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { experimentGroupName } = useRequiredPathParams([ROUTE_PARAMS.experimentGroupName]);
  const { data: group, error } = useGetExperimentGroup(workspace, experimentGroupName);
  // The insight is a group-level concept, reached via the group's insight_id.
  const { data: insight } = useOptimizerGetInsight(workspace, group?.insight_id ?? '', {
    query: { enabled: OPTIMIZER_ENABLED && Boolean(group?.insight_id) },
  });
  const [editOpen, setEditOpen] = useState(false);

  // Pareto (cost-vs-accuracy) view visibility, persisted per group. Hidden by default.
  const [storedParetoVisible, setParetoVisible] = useLocalStorage<boolean>(
    `nemo-studio:experiment-group-pareto:${group?.id ?? ''}`,
    false
  );
  const paretoVisible = storedParetoVisible ?? false;

  useBreadcrumbs({
    items: [
      { href: getExperimentRoute(workspace), slotLabel: 'Experiment Groups' },
      { slotLabel: experimentGroupName },
    ],
  });

  return (
    <AccessibleTitle title={experimentGroupName}>
      <Stack className="h-full overflow-auto" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading={experimentGroupName}
          slotDescription={group?.description || undefined}
          slotActions={
            <Button kind="secondary" disabled={!group} onClick={() => setEditOpen(true)}>
              <Pencil />
              Edit
            </Button>
          }
        />
        {error ? (
          <ErrorMessage message="Failed to load experiment group." />
        ) : (
          <>
            {group && (
              <ExperimentGroupEditModal
                open={editOpen}
                onClose={() => setEditOpen(false)}
                workspace={workspace}
                group={group}
              />
            )}
            <ExperimentGroupMetrics experimentGroupName={experimentGroupName} />
            {(insight?.description || group?.summary) && (
              <div className="flex items-start gap-density-lg">
                {insight?.description ? (
                  <Card className="min-w-0 flex-1">
                    <Stack className="gap-density-md">
                      <Flex className="items-start justify-between gap-density-md">
                        <Text kind="label/bold/lg">Insight description</Text>
                        <OriginatingInsightLink insightId={insight.id} />
                      </Flex>
                      <Text kind="body/regular/md">{insight.description}</Text>
                    </Stack>
                  </Card>
                ) : null}
                {group?.summary ? (
                  <Card className="min-w-0 flex-1">
                    <Stack className="gap-density-md">
                      <Text kind="title/sm">Summary</Text>
                      <Text kind="body/regular/md">{group.summary}</Text>
                    </Stack>
                  </Card>
                ) : null}
              </div>
            )}
            <div className="flex flex-col gap-4 border-t border-base pt-4">
              <div className="flex items-center gap-3">
                <Text kind="title/sm">Evaluations</Text>
                {group && (
                  <Button
                    kind="tertiary"
                    aria-pressed={paretoVisible}
                    onClick={() => setParetoVisible(!paretoVisible)}
                  >
                    <ChartScatter width={12} height={12} className="text-brand" />
                    {paretoVisible ? 'Hide Pareto' : 'Pareto view'}
                  </Button>
                )}
              </div>
              {group && <ExperimentGroupDataView group={group} paretoVisible={paretoVisible} />}
            </div>
          </>
        )}
      </Stack>
    </AccessibleTitle>
  );
};
