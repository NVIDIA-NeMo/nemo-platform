// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { server } from '@studio/mocks/node';
import { SubmitEvaluationModal } from '@studio/routes/agents/AgentEvaluationsRoute/components/SubmitEvaluationModal';
import { renderRoute, screen } from '@studio/tests/util/render';
import { within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

const workspace = workspace1.workspace;
const agentsUrl = `${PLATFORM_BASE_URL}/apis/agents/v2/workspaces/${workspace}/agents`;
const evaluateUrl = `${PLATFORM_BASE_URL}/apis/agents/v2/workspaces/${workspace}/jobs/evaluate`;

describe('SubmitEvaluationModal', () => {
  it('evaluates a registered external agent through its endpoint URL', async () => {
    const user = userEvent.setup();
    let captured: { spec?: { agent?: string } } = {};
    server.use(
      http.get(agentsUrl, () =>
        HttpResponse.json({
          data: [
            {
              name: 'remote-agent',
              workspace,
              config_format: 'external-endpoint-v1',
              config: {
                endpoint_url: 'https://agents.example.com/v1',
                protocol: 'nat-http-v1',
              },
            },
          ],
          pagination: { total_results: 1 },
        })
      ),
      http.get(evaluateUrl, () =>
        HttpResponse.json({
          data: [
            {
              name: 'prior-external-eval',
              workspace,
              status: 'completed',
              created_at: '2026-07-21T00:00:00Z',
              updated_at: '2026-07-21T00:00:00Z',
              spec: {
                agent: 'https://agents.example.com/v1',
                eval_config: 'external-eval.yml',
                eval_config_fileset: 'external-eval',
              },
            },
          ],
          pagination: { total_results: 1 },
        })
      ),
      http.post(evaluateUrl, async ({ request }) => {
        captured = (await request.json()) as typeof captured;
        return HttpResponse.json({
          name: 'remote-agent-eval',
          workspace,
          spec: captured.spec,
        });
      })
    );

    renderRoute(
      <SubmitEvaluationModal
        open
        onClose={() => undefined}
        workspace={workspace}
        agent="remote-agent"
      />
    );
    const dialog = await screen.findByRole('dialog');
    expect(
      await within(dialog).findByText(/call the registered external endpoint directly/)
    ).toBeInTheDocument();
    expect(await within(dialog).findByRole('combobox')).toHaveTextContent('external-eval');
    await user.click(within(dialog).getByRole('button', { name: 'Submit' }));

    expect(await screen.findByText(/Evaluation "remote-agent-eval" submitted/)).toBeInTheDocument();
    expect(captured).toMatchObject({
      spec: { agent: 'https://agents.example.com/v1' },
    });
  });
});
