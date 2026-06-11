// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PageHeader, Stack } from '@nvidia/foundations-react-core';
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

  useBreadcrumbs({
    items: [
      { href: getExperimentRoute(workspace), slotLabel: 'Experiments' },
      { slotLabel: experimentGroupName },
    ],
  });

  return (
    <AccessibleTitle title={experimentGroupName}>
      <Stack className="h-full overflow-auto" gap="density-2xl" padding="density-2xl">
        <PageHeader className="p-0" slotHeading={experimentGroupName} />
        <ExperimentGroupMetrics experimentGroupName={experimentGroupName} />
        <ExperimentGroupDataView experimentGroupName={experimentGroupName} />
      </Stack>
    </AccessibleTitle>
  );
};
