// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getAgentsListDeploymentsQueryKey } from '@nemo/sdk/generated/agents/api';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { server } from '@studio/mocks/node';
import { CreateDeploymentModal } from '@studio/routes/agents/AgentDeploymentsListRoute/CreateDeploymentModal';
import { renderRoute, screen, waitFor } from '@studio/tests/util/render';
import { within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

const workspace = workspace1.workspace;
const agent = 'nemo-agent-local-poc';
const deploymentsUrl = `${PLATFORM_BASE_URL}${getAgentsListDeploymentsQueryKey(':workspace')[0]}`;

interface CapturedDeployment {
  agent?: string;
  name?: string;
  deployment_mode?: string;
  image?: string;
}

const renderModal = () =>
  renderRoute(<CreateDeploymentModal open onClose={vi.fn()} workspace={workspace} agent={agent} />);

const captureCreate = (): { body: CapturedDeployment } => {
  const captured: { body: CapturedDeployment } = { body: {} };
  server.use(
    http.post(deploymentsUrl, async ({ request }) => {
      captured.body = (await request.json()) as CapturedDeployment;
      return HttpResponse.json({
        ...captured.body,
        name: captured.body.name ?? 'generated-deployment',
        workspace,
        status: 'pending',
      });
    })
  );
  return captured;
};

const getDeploymentDialog = async (): Promise<HTMLDialogElement> => {
  const dialog = await screen.findByRole('dialog', { name: 'Deploy Agent' });
  if (!(dialog instanceof HTMLDialogElement)) {
    throw new Error('Deploy Agent did not render as a dialog');
  }
  return dialog;
};

describe('CreateDeploymentModal', () => {
  it('creates a Docker deployment with the selected container image', async () => {
    const user = userEvent.setup();
    const captured = captureCreate();
    renderModal();

    const dialog = await getDeploymentDialog();
    await user.click(within(dialog).getByRole('combobox', { name: 'Runtime' }));
    await user.click(await screen.findByRole('option', { name: 'Docker' }));
    await user.type(
      within(dialog).getByRole('textbox', { name: 'Container Image' }),
      'nvcr.io/example/nemo-agent:poc'
    );
    await user.click(within(dialog).getByRole('button', { name: 'Deploy' }));

    await waitFor(() =>
      expect(captured.body).toEqual({
        agent,
        deployment_mode: 'docker',
        image: 'nvcr.io/example/nemo-agent:poc',
      })
    );
  });

  it('requires an image for container deployments', async () => {
    const user = userEvent.setup();
    renderModal();

    const dialog = await getDeploymentDialog();
    await user.click(within(dialog).getByRole('combobox', { name: 'Runtime' }));
    await user.click(await screen.findByRole('option', { name: 'Docker' }));
    await user.click(within(dialog).getByRole('button', { name: 'Deploy' }));

    expect(
      await within(dialog).findByText(
        'Container image is required for Docker and Kubernetes deployments'
      )
    ).toBeInTheDocument();
  });
});
