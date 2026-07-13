// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { mockGuardrailConfigs } from '@studio/mocks/handlers/guardrails';
import { server } from '@studio/mocks/node';
import { GuardrailDetailRoute } from '@studio/routes/guardrails/GuardrailDetailRoute';
import { getGuardrailDetailRoute } from '@studio/routes/utils';
import { XL_SELECTOR_TIMEOUT } from '@studio/tests/util/constants';
import { renderRoute, screen } from '@studio/tests/util/render';
import { within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { delay, http, HttpResponse } from 'msw';

const WORKSPACE = 'default';

const routes = [
  {
    path: ROUTES.workspace.guardrailDetail,
    element: <GuardrailDetailRoute />,
  },
  {
    path: ROUTES.workspace.guardrails,
    element: <div data-testid="guardrails-list">LIST</div>,
  },
];

const renderDetail = (name: string) =>
  renderRoute(undefined, {
    history: getGuardrailDetailRoute(WORKSPACE, name),
    routes,
  });

describe('GuardrailDetailRoute', () => {
  it('renders the config details from the detail endpoint', async () => {
    renderDetail('pii-filter');

    expect(
      await screen.findByText('pii-filter', undefined, { timeout: XL_SELECTOR_TIMEOUT })
    ).toBeInTheDocument();
    expect(screen.getByText('Blocks PII in user inputs and outputs')).toBeInTheDocument();
    // pii-filter has 2 models and 4 rail flows (2 input + 2 output).
    expect(screen.getAllByText('2').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('4').length).toBeGreaterThanOrEqual(1);
    // Raw config block.
    expect(screen.getByText('Config')).toBeInTheDocument();
  });

  it('shows the Edit button disabled', async () => {
    renderDetail('pii-filter');
    await screen.findByText('pii-filter', undefined, { timeout: XL_SELECTOR_TIMEOUT });
    expect(screen.getByRole('button', { name: 'Edit' })).toBeDisabled();
  });

  it('shows a loading state while fetching', async () => {
    server.use(
      http.get(
        `${PLATFORM_BASE_URL}/apis/guardrails/v2/workspaces/:workspace/configs/:name`,
        async () => {
          await delay();
          return HttpResponse.json(mockGuardrailConfigs[0]);
        }
      )
    );
    renderDetail('pii-filter');
    expect(await screen.findByText('Loading guardrail config...')).toBeInTheDocument();
  });

  it('shows an error state when the config cannot be loaded', async () => {
    renderDetail('does-not-exist');
    expect(
      await screen.findByText('Failed to load guardrail config.', undefined, {
        timeout: XL_SELECTOR_TIMEOUT,
      })
    ).toBeInTheDocument();
  });

  it('deletes the config and navigates back to the list', async () => {
    const user = userEvent.setup();
    renderDetail('pii-filter');
    await screen.findByText('pii-filter', undefined, { timeout: XL_SELECTOR_TIMEOUT });

    await user.click(screen.getByRole('button', { name: 'Delete' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }));

    expect(
      await screen.findByTestId('guardrails-list', undefined, { timeout: XL_SELECTOR_TIMEOUT })
    ).toBeInTheDocument();
  });
});
