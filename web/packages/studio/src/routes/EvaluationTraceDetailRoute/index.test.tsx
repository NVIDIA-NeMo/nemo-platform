// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { EvaluationTraceDetailRoute } from '@studio/routes/EvaluationTraceDetailRoute';
import { getEvaluationTraceDetailRoute } from '@studio/routes/utils';
import { renderRoute, screen } from '@studio/tests/util/render';

const WORKSPACE = 'default';
const EXPERIMENT_GROUP = 'my-group';
const EXPERIMENT_NAME = 'my-experiment';
// Reuses the pre-wired mock trace from @studio/mocks/intake/telemetry
const TRACE_ID = 'trace-agent-run-001';

const renderTraceDetail = () =>
  renderRoute(undefined, {
    history: getEvaluationTraceDetailRoute(WORKSPACE, EXPERIMENT_GROUP, EXPERIMENT_NAME, TRACE_ID),
    routes: [
      {
        path: '/workspaces/:workspace/experiment/:experimentGroupName/:evaluationName/traces/:traceId',
        element: <EvaluationTraceDetailRoute />,
      },
    ],
  });

describe('EvaluationTraceDetailRoute', () => {
  it('renders the trace detail content', async () => {
    renderTraceDetail();
    expect(await screen.findByText('Trace Answer customer policy question')).toBeInTheDocument();
  });

  it('renders the evaluation context panel', async () => {
    renderTraceDetail();
    await screen.findByText('Trace Answer customer policy question');
    expect(screen.getByText('Evaluation Context')).toBeInTheDocument();
  });

  it('does not render an Intake link in the page content', async () => {
    renderTraceDetail();
    await screen.findByText('Trace Answer customer policy question');
    // "Intake" should not appear anywhere in the rendered page content
    // (breadcrumbs are rendered by WorkspaceLayout, absent from unit tests, but the
    // page body itself should have no Intake references)
    expect(screen.queryByRole('link', { name: 'Intake' })).not.toBeInTheDocument();
  });
});
