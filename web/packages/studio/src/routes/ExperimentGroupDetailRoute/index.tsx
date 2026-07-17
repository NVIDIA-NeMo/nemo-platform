// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { useGetExperimentGroup } from '@nemo/sdk/generated/platform/api';
import {
  Anchor,
  Badge,
  Button,
  Card,
  Flex,
  PageHeader,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { useOptimizerGetInsight } from '@studio/api/optimizer';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { ExperimentGroupDataView } from '@studio/components/dataViews/ExperimentGroupDataView';
import { ExperimentGroupEditModal } from '@studio/components/ExperimentGroupEditModal';
import { OriginatingInsightLink } from '@studio/components/OriginatingInsightLink';
import { LINK_DOCS_STUDIO_EVALUATION } from '@studio/constants/links';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { ExperimentGroupMetrics } from '@studio/routes/ExperimentGroupDetailRoute/ExperimentGroupMetrics';
import { getExperimentRoute } from '@studio/routes/utils';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { Pencil } from 'lucide-react';
import { type FC, useState } from 'react';

export const ExperimentGroupDetailRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { experimentGroupName } = useRequiredPathParams([ROUTE_PARAMS.experimentGroupName]);
  const { data: group, error } = useGetExperimentGroup(workspace, experimentGroupName);
  // The insight is a group-level concept, reached via the group's insight_id.
  const { data: insight } = useOptimizerGetInsight(workspace, group?.insight_id ?? '');
  const [editOpen, setEditOpen] = useState(false);

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
          slotDescription={
            <>
              A experiment is a group of evaluation runs aligned toward a common objective.{' '}
              <Anchor href={LINK_DOCS_STUDIO_EVALUATION} target="_blank">
                Learn more
              </Anchor>
            </>
          }
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
            <div className="flex items-start gap-density-lg">
              {insight?.description ? (
                <Card className="min-w-0 flex-1">
                  <Flex className="items-start gap-density-md">
                    <OriginatingInsightLink insightId={insight.id} />
                    <Stack className="min-w-0 flex-1 gap-density-md">
                      <Text kind="label/bold/lg">Insight description</Text>
                      <Text kind="body/regular/md">{insight.description}</Text>
                    </Stack>
                  </Flex>
                </Card>
              ) : null}
              <Card className="min-w-0 flex-1">
                <Stack className="gap-density-md">
                  <Text kind="title/sm">Summary</Text>
                  <Text kind="body/regular/md">{group?.description || '—'}</Text>
                </Stack>
              </Card>
            </div>
            <div className="flex flex-col gap-4">
              <div className="flex items-center gap-3">
                <Text kind="title/sm">Evaluations</Text>
                {group?.evaluation_count !== undefined && (
                  <Badge color="gray" kind="solid" className="text-sm">
                    {group.evaluation_count}
                  </Badge>
                )}
              </div>
              {group && <ExperimentGroupDataView group={group} />}
            </div>
          </>
        )}
      </Stack>
    </AccessibleTitle>
  );
};
