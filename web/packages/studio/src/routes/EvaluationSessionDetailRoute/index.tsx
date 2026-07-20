// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { SessionDetailRouteContext } from '@studio/components/IntakeDetail/SessionDetailView';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { SessionDetailContent } from '@studio/routes/IntakeSessionDetailRoute';
import {
  getEvaluationDetailRoute,
  getEvaluationSessionDetailRoute,
  getExperimentGroupDetailRoute,
  getExperimentRoute,
} from '@studio/routes/utils';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { type FC, useMemo } from 'react';

export const EvaluationSessionDetailRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { sessionId, experimentGroupName, evaluationName } = useRequiredPathParams([
    ROUTE_PARAMS.sessionId,
    ROUTE_PARAMS.experimentGroupName,
    ROUTE_PARAMS.evaluationName,
  ]);
  const routeContext = useMemo<SessionDetailRouteContext>(
    () => ({
      kind: 'evaluation',
      parentBreadcrumbs: [
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
      getSessionHref: (targetSessionId) =>
        getEvaluationSessionDetailRoute(
          workspace,
          experimentGroupName,
          evaluationName,
          targetSessionId
        ),
    }),
    [workspace, experimentGroupName, evaluationName]
  );

  return <SessionDetailContent sessionId={sessionId} routeContext={routeContext} />;
};
