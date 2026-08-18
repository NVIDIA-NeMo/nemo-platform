// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@nemo/common/src/components/ErrorPanel';
import { AGENTS_ENABLED, MONITOR_ENABLED } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { iconColorClass } from '@studio/routes/constants';
import {
  agentsRoutes,
  getAgentMonitorRoute,
} from '@studio/routes/utils';
import { DatabaseCheck } from 'lucide-react';
import { lazy } from 'react';
import type { RouteObject } from 'react-router';

const AgentsListRoute =
  AGENTS_ENABLED &&
  lazy(() =>
    import('@studio/routes/agents/AgentsListRoute').then((m) => ({
      default: m.AgentsListRoute,
    }))
  );
const AgentDetailRoute =
  AGENTS_ENABLED &&
  lazy(() =>
    import('@studio/routes/agents/AgentDetailRoute').then((m) => ({
      default: m.AgentDetailRoute,
    }))
  );
const AgentMonitorRoute = lazy(() =>
  import('@studio/routes/agents/AgentMonitorRoute').then((m) => ({
    default: m.AgentMonitorRoute,
  }))
);
const AgentEvaluationDetailRoute =
  AGENTS_ENABLED &&
  lazy(() =>
    import('@studio/routes/agents/AgentEvaluationsRoute').then((m) => ({
      default: m.AgentEvaluationDetailRoute,
    }))
  );

export const agentRoutes: RouteObject[] = agentsRoutes([
  {
    path: ROUTES.workspace.agentsList,
    element: AgentsListRoute ? <AgentsListRoute /> : null,
    errorElement: <ErrorPanel title="Agents" />,
  },
  ...(MONITOR_ENABLED
    ? [
        {
          path: ROUTES.workspace.agentMonitor,
          element: <AgentMonitorRoute />,
          errorElement: <ErrorPanel title="Monitor" />,
        },
      ]
    : []),
  {
    path: ROUTES.workspace.agentEvaluationDetail,
    element: AgentEvaluationDetailRoute ? <AgentEvaluationDetailRoute /> : null,
    errorElement: <ErrorPanel title="Agent Evaluation" />,
  },
  {
    path: ROUTES.workspace.agentDetail,
    element: AgentDetailRoute ? <AgentDetailRoute /> : null,
    errorElement: <ErrorPanel title="Agent details" />,
  },
]);

export const getAgentSideNavItems = (workspace: string) =>
  AGENTS_ENABLED
    ? [
        ...(MONITOR_ENABLED
          ? [
              {
                id: 'agent-monitor',
                slotIcon: <DatabaseCheck className={iconColorClass} />,
                slotLabel: 'Monitor',
                href: getAgentMonitorRoute(workspace),
              },
            ]
          : []),
      ]
    : [];
