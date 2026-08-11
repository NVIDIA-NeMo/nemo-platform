// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { AGENTS_ENABLED } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { iconColorClass } from '@studio/routes/constants';
import {
  agentsRoutes,
  getAgentEvaluationsListRoute,
  getAgentMonitorRoute,
} from '@studio/routes/utils';
import { Form, DatabaseCheck } from 'lucide-react';
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
const AgentMonitorRoute =
  AGENTS_ENABLED &&
  lazy(() =>
    import('@studio/routes/agents/AgentMonitorRoute').then((m) => ({
      default: m.AgentMonitorRoute,
    }))
  );
const AgentEvaluationsListRoute =
  AGENTS_ENABLED &&
  lazy(() =>
    import('@studio/routes/agents/AgentEvaluationsRoute').then((m) => ({
      default: m.AgentEvaluationsListRoute,
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
  {
    path: ROUTES.workspace.agentMonitor,
    element: AgentMonitorRoute ? <AgentMonitorRoute /> : null,
    errorElement: <ErrorPanel title="Monitor" />,
  },
  {
    path: ROUTES.workspace.agentEvaluationsList,
    element: AgentEvaluationsListRoute ? <AgentEvaluationsListRoute /> : null,
    errorElement: <ErrorPanel title="Agent Evaluations" />,
  },
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
        {
          id: 'agent-evaluations',
          slotIcon: <Form className={iconColorClass} />,
          // Qualified: the rail hoists this out of Agents, next to the model evaluations link.
          slotLabel: 'Agent Evaluations',
          href: getAgentEvaluationsListRoute(workspace),
        },
        {
          id: 'agent-monitor',
          slotIcon: <DatabaseCheck className={iconColorClass} />,
          slotLabel: 'Monitor',
          href: getAgentMonitorRoute(workspace),
        },
      ]
    : [];
