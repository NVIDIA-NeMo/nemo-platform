// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { type BreadcrumbsItemProps } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { IntakeTraceDetailContent } from '@studio/routes/IntakeTraceDetailRoute';
import {
  getExperimentDetailRoute,
  getExperimentGroupDetailRoute,
  getExperimentRoute,
} from '@studio/routes/utils';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { type FC, useMemo } from 'react';

export const ExperimentTraceDetailRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { traceId, experimentGroupName, experimentName } = useRequiredPathParams([
    ROUTE_PARAMS.traceId,
    ROUTE_PARAMS.experimentGroupName,
    ROUTE_PARAMS.experimentName,
  ]);

  const parentBreadcrumbs = useMemo<BreadcrumbsItemProps[]>(
    () => [
      { slotLabel: 'Experiment Groups', href: getExperimentRoute(workspace) },
      {
        slotLabel: experimentGroupName,
        href: getExperimentGroupDetailRoute(workspace, experimentGroupName),
      },
      {
        slotLabel: experimentName,
        href: getExperimentDetailRoute(workspace, experimentGroupName, experimentName),
      },
    ],
    [workspace, experimentGroupName, experimentName]
  );

  return <IntakeTraceDetailContent traceId={traceId} parentBreadcrumbs={parentBreadcrumbs} />;
};
