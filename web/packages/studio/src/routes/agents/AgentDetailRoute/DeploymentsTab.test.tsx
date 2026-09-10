// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AgentDeployment } from '@nemo/sdk/generated/agents/schema/AgentDeployment';
import { DeploymentsTab } from '@studio/routes/agents/AgentDetailRoute/DeploymentsTab';
import { renderRoute, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';

const LONG_ERROR =
  "No container-reachable inference base URL for k8s deployment: platform base URL 'http://127.0.0.1:8080' is not usable from an agent pod and no internal API Service URL is set. Set NEMO_INTERNAL_BASE_URL / NMP_INTERNAL_BASE_URL (or deploy with a cluster-internal gateway address).";

const failedDeployment = {
  name: 'calculator-agent-2-17aa2130',
  workspace: 'default',
  status: 'failed',
  error: LONG_ERROR,
} as AgentDeployment;

const renderTab = (deployments: AgentDeployment[]) =>
  renderRoute(
    <DeploymentsTab
      agentName="calculator-agent"
      deployments={deployments}
      isDeploymentsLoading={false}
      isDeploying={false}
      onDeploy={vi.fn()}
      onChat={vi.fn()}
      onDelete={vi.fn()}
      onViewLogs={vi.fn()}
      canDeploy
      workspace="default"
      canPackage
    />
  );

describe('DeploymentsTab', () => {
  it('makes a long failure message readable instead of ellipsising it away', async () => {
    const user = userEvent.setup();
    renderTab([failedDeployment]);

    const toggle = screen.getByRole('button', { name: 'Show full error' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');

    await user.click(toggle);

    const expanded = screen.getByRole('button', { name: 'Show less' });
    expect(expanded).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText(LONG_ERROR)).toBeInTheDocument();
  });

  it('keeps packaging out of the way when container deployments are off', () => {
    renderTab([failedDeployment]);

    expect(screen.queryByRole('button', { name: /Container image/ })).not.toBeInTheDocument();
  });

  it('names the image a deployment is running, since an agent has many over time', () => {
    renderTab([
      {
        name: 'calculator-agent-1',
        workspace: 'default',
        status: 'running',
        image: 'nemo-agents/default/calculator-agent-9594db954f89:26.09.04',
      } as AgentDeployment,
    ]);

    expect(
      screen.getByText('nemo-agents/default/calculator-agent-9594db954f89:26.09.04')
    ).toBeInTheDocument();
  });

  it('offers no error toggle when a deployment has not failed', () => {
    renderTab([
      {
        name: 'calculator-agent-1',
        workspace: 'default',
        status: 'running',
        endpoint: 'http://localhost:9001',
      } as AgentDeployment,
    ]);

    expect(screen.queryByRole('button', { name: /error/i })).not.toBeInTheDocument();
  });
});
