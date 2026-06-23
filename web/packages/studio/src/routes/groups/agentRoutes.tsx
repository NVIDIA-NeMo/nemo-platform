// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorPanel } from '@studio/components/ErrorPanel';
import { AGENTS_ENABLED } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { agentsRoutes } from '@studio/routes/utils';
import { lazy } from 'react';
import type { RouteObject } from 'react-router-dom';

const AgentsListRoute =
  AGENTS_ENABLED &&
  lazy(() =>
    import('@studio/routes/agents/AgentsListRoute').then((m) => ({
      default: m.AgentsListRoute,
    }))
  );
const AgentOptimizationsRoute =
  AGENTS_ENABLED &&
  lazy(() =>
    import('@studio/routes/agents/AgentSuggestionsRoute').then((m) => ({
      default: m.AgentOptimizationsRoute,
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
    path: ROUTES.workspace.agentOptimizations,
    element: AgentOptimizationsRoute ? <AgentOptimizationsRoute /> : null,
    errorElement: <ErrorPanel title="Optimizations" />,
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
    element: AgentsListRoute ? <AgentsListRoute /> : null,
    errorElement: <ErrorPanel title="Agents" />,
  },
]);
