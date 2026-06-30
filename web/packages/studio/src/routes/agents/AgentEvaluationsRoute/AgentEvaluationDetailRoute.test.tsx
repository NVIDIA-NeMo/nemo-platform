// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ROUTES } from '@studio/constants/routes';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { AgentEvaluationDetailRoute } from '@studio/routes/agents/AgentEvaluationsRoute';
import { getAgentEvaluationDetailRoute } from '@studio/routes/utils';
import { renderRoute, screen } from '@studio/tests/util/render';

const workspace = workspace1.workspace;
const JOB_NAME = 'eval-missing';

const renderDetail = () =>
  renderRoute(<AgentEvaluationDetailRoute />, {
    history: getAgentEvaluationDetailRoute(workspace, JOB_NAME),
    routes: [
      { path: ROUTES.workspace.agentEvaluationDetail, element: <AgentEvaluationDetailRoute /> },
    ],
  });

describe('AgentEvaluationDetailRoute', () => {
  it('renders the not-found state when the job lookup returns null', async () => {
    // Default MSW handler returns ``{ data: [] }`` for the list endpoint;
    // there's no handler for the single-job GET, so MSW falls through to a
    // 404 → fetchAgentEvalJob resolves to null → not-found UI.
    renderDetail();
    expect(await screen.findByText('Evaluation not found')).toBeInTheDocument();
  });
});
