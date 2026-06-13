// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ROUTES } from '@studio/constants/routes';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { AgentEvaluationsListRoute } from '@studio/routes/agents/AgentEvaluationsRoute';
import { getAgentEvaluationsListRoute } from '@studio/routes/utils';
import { renderRoute, screen } from '@studio/tests/util/render';

const workspace = workspace1.workspace;

const renderList = () =>
  renderRoute(<AgentEvaluationsListRoute />, {
    history: getAgentEvaluationsListRoute(workspace),
    routes: [
      { path: ROUTES.workspace.agentEvaluationsList, element: <AgentEvaluationsListRoute /> },
    ],
  });

describe('AgentEvaluationsListRoute', () => {
  it('renders the page header and submit button', async () => {
    renderList();
    expect(await screen.findByText('Agent Evaluations')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'New evaluation' })).toBeInTheDocument();
  });

  it('shows the empty state when no eval jobs are returned (default mock)', async () => {
    renderList();
    expect(await screen.findByText('No evaluation jobs yet')).toBeInTheDocument();
  });
});
