// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { type BreadcrumbsItemProps } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { IntakeTraceDetailContent } from '@studio/routes/IntakeTraceDetailRoute';
import {
  getEvaluationDetailRoute,
  getExperimentGroupDetailRoute,
  getExperimentRoute,
} from '@studio/routes/utils';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { type FC, useMemo } from 'react';

export const EvaluationTraceDetailRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { traceId, experimentGroupName, evaluationName } = useRequiredPathParams([
    ROUTE_PARAMS.traceId,
    ROUTE_PARAMS.experimentGroupName,
    ROUTE_PARAMS.evaluationName,
  ]);

  const parentBreadcrumbs = useMemo<BreadcrumbsItemProps[]>(
    () => [
      { slotLabel: 'Experiment Groups', href: getExperimentRoute(workspace) },
      {
        slotLabel: experimentGroupName,
        href: getExperimentGroupDetailRoute(workspace, experimentGroupName),
      },
      {
        slotLabel: evaluationName,
        href: getEvaluationDetailRoute(workspace, experimentGroupName, evaluationName),
      },
    ],
    [workspace, experimentGroupName, evaluationName]
  );

  return (
    <IntakeTraceDetailContent
      traceId={traceId}
      parentBreadcrumbs={parentBreadcrumbs}
      showTestCaseTitle
    />
  );
};
