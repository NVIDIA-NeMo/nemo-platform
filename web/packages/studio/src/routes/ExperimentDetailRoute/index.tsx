// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PageHeader, Stack } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { ExperimentSessionsDataView } from '@studio/components/dataViews/ExperimentSessionsDataView';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { ExperimentDetailMetrics } from '@studio/routes/ExperimentDetailRoute/ExperimentDetailMetrics';
import { getExperimentRoute, getExperimentGroupDetailRoute } from '@studio/routes/utils';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { type FC } from 'react';

export const ExperimentDetailRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { experimentGroupName, experimentName } = useRequiredPathParams([
    ROUTE_PARAMS.experimentGroupName,
    ROUTE_PARAMS.experimentName,
  ]);

  useBreadcrumbs({
    items: [
      { href: getExperimentRoute(workspace), slotLabel: 'Experiments' },
      {
        href: getExperimentGroupDetailRoute(workspace, experimentGroupName),
        slotLabel: experimentGroupName,
      },
      { slotLabel: experimentName },
    ],
  });

  return (
    <AccessibleTitle title={experimentName}>
      <Stack className="h-full overflow-auto" gap="density-2xl" padding="density-2xl">
        <PageHeader className="p-0" slotHeading={experimentName} />
        <ExperimentDetailMetrics experimentName={experimentName} />
        <ExperimentSessionsDataView
          experimentName={experimentName}
          experimentGroupName={experimentGroupName}
        />
      </Stack>
    </AccessibleTitle>
  );
};
