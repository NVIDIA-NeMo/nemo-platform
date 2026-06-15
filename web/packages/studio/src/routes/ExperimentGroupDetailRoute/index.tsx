// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useGetExperimentGroup } from '@nemo/sdk/generated/platform/api';
import { Badge, PageHeader, Stack, Text } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { ExperimentGroupDataView } from '@studio/components/dataViews/ExperimentGroupDataView';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { ExperimentGroupMetrics } from '@studio/routes/ExperimentGroupDetailRoute/ExperimentGroupMetrics';
import { getExperimentRoute } from '@studio/routes/utils';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { type FC } from 'react';

export const ExperimentGroupDetailRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { experimentGroupName } = useRequiredPathParams([ROUTE_PARAMS.experimentGroupName]);
  const { data: group } = useGetExperimentGroup(workspace, experimentGroupName);

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
        />
        <ExperimentGroupMetrics experimentGroupName={experimentGroupName} />
        <div className="flex flex-col gap-4 border-t border-base pt-4">
          <div className="flex items-center gap-3">
            <Text kind="title/sm">Experiments</Text>
            {group?.experiment_count !== undefined && (
              <Badge color="gray" kind="solid" className="text-sm">
                {group.experiment_count}
              </Badge>
            )}
          </div>
          <ExperimentGroupDataView experimentGroupName={experimentGroupName} />
        </div>
      </Stack>
    </AccessibleTitle>
  );
};
