// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { IntakeTraceDetailRoute } from '@studio/routes/IntakeTraceDetailRoute';
import { renderRoute, screen } from '@studio/tests/util/render';

const renderTraceDetail = (traceId: string) =>
  renderRoute(undefined, {
    history: `/workspaces/default/intake/traces/${traceId}`,
    routes: [
      {
        path: '/workspaces/:workspace/intake/traces/:traceId',
        element: <IntakeTraceDetailRoute />,
      },
    ],
  });

describe('IntakeTraceDetailRoute', () => {
  it('renders evaluation context only when present and filters spans to the trace', async () => {
    renderTraceDetail('trace-agent-run-001');

    expect(await screen.findByText('Trace Answer customer policy question')).toBeInTheDocument();
    expect(screen.getByText('Evaluation Context')).toBeInTheDocument();
    expect(await screen.findByText('Generate final response')).toBeInTheDocument();
    expect(screen.queryByText('Retrieve deployment troubleshooting steps')).not.toBeInTheDocument();
  });

  it('omits evaluation context when the trace has none', async () => {
    renderTraceDetail('trace-agent-run-002');

    expect(
      await screen.findByText('Trace Retrieve deployment troubleshooting steps')
    ).toBeInTheDocument();
    expect(screen.queryByText('Evaluation Context')).not.toBeInTheDocument();
  });
});
