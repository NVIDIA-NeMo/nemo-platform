// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { server } from '@studio/mocks/node';
import { RunOptimizationModal } from '@studio/routes/agents/AgentSuggestionsRoute/components/RunOptimizationModal';
import { renderRoute, screen } from '@studio/tests/util/render';
import { within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

const workspace = workspace1.workspace;
const agentsUrl = `${PLATFORM_BASE_URL}/apis/agents/v2/workspaces/${workspace}/agents`;
const optimizeUrl = `${PLATFORM_BASE_URL}/apis/agents/v2/workspaces/${workspace}/jobs/optimize`;

describe('RunOptimizationModal', () => {
  it('submits the selected agent and absolute optimization config path', async () => {
    const user = userEvent.setup();
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.get(agentsUrl, () =>
        HttpResponse.json({
          data: [{ name: 'support-agent', workspace }],
          pagination: { total_results: 1 },
        })
      ),
      http.post(optimizeUrl, async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          name: 'support-agent-hpo',
          spec: (captured as { spec: Record<string, unknown> }).spec,
        });
      })
    );

    renderRoute(<RunOptimizationModal open onClose={() => undefined} workspace={workspace} />);
    const dialog = await screen.findByRole('dialog');
    await user.click(await within(dialog).findByRole('combobox', { name: 'Agent' }));
    await user.click(await screen.findByRole('option', { name: 'support-agent' }));
    await user.type(
      within(dialog).getByRole('textbox', { name: 'Optimization YAML path' }),
      '/workspace/configs/support-optimize.yml'
    );
    await user.type(
      within(dialog).getByRole('textbox', { name: 'Job name (optional)' }),
      'support-agent-hpo'
    );
    await user.click(within(dialog).getByRole('button', { name: 'Start tuning' }));

    expect(
      await screen.findByText(/Hyperparameter tuning "support-agent-hpo" submitted/)
    ).toBeInTheDocument();
    expect(captured).toMatchObject({
      name: 'support-agent-hpo',
      spec: {
        agent: 'support-agent',
        optimize_config: '/workspace/configs/support-optimize.yml',
        workspace,
      },
    });
  });

  it('rejects a browser-local relative path before submission', async () => {
    const user = userEvent.setup();
    server.use(
      http.get(agentsUrl, () =>
        HttpResponse.json({ data: [{ name: 'support-agent', workspace }], pagination: {} })
      )
    );

    renderRoute(<RunOptimizationModal open onClose={() => undefined} workspace={workspace} />);
    const dialog = await screen.findByRole('dialog');
    await user.click(await within(dialog).findByRole('combobox', { name: 'Agent' }));
    await user.click(await screen.findByRole('option', { name: 'support-agent' }));
    await user.type(
      within(dialog).getByRole('textbox', { name: 'Optimization YAML path' }),
      './support-optimize.yml'
    );
    await user.click(within(dialog).getByRole('button', { name: 'Start tuning' }));

    expect(await within(dialog).findByText('Enter an absolute platform path')).toBeInTheDocument();
  });

  it('excludes external endpoints from hyperparameter tuning', async () => {
    const user = userEvent.setup();
    server.use(
      http.get(agentsUrl, () =>
        HttpResponse.json({
          data: [
            {
              name: 'remote-agent',
              workspace,
              config_format: 'external-endpoint-v1',
              config: { endpoint_url: 'https://agents.example.com/v1' },
            },
            { name: 'support-agent', workspace, config_format: 'nat-workflow-v1' },
          ],
          pagination: { total_results: 2 },
        })
      )
    );

    renderRoute(<RunOptimizationModal open onClose={() => undefined} workspace={workspace} />);
    const dialog = await screen.findByRole('dialog');
    expect(
      await within(dialog).findByText(/External endpoint agents are not listed here/)
    ).toBeInTheDocument();
    await user.click(await within(dialog).findByRole('combobox', { name: 'Agent' }));

    expect(await screen.findByRole('option', { name: 'support-agent' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'remote-agent' })).not.toBeInTheDocument();
  });
});
