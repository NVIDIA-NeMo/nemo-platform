// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { mockGuardrailConfigs } from '@studio/mocks/handlers/guardrails';
import { server } from '@studio/mocks/node';
import { GuardrailConfigTab } from '@studio/routes/guardrails/GuardrailConfigTab';
import { GuardrailDetailRoute } from '@studio/routes/guardrails/GuardrailDetailRoute';
import { getGuardrailDetailRoute } from '@studio/routes/utils';
import { XL_SELECTOR_TIMEOUT } from '@studio/tests/util/constants';
import { renderRoute, screen, waitFor } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';
import { delay, http, HttpResponse } from 'msw';
import { Navigate } from 'react-router-dom';

const WORKSPACE = 'default';

beforeEach(() => {
  localStorage.clear();
});

const routes = [
  {
    path: ROUTES.workspace.guardrailDetail,
    element: <GuardrailDetailRoute />,
    children: [
      { index: true, element: <Navigate to="config" replace /> },
      { path: ROUTES.workspace.guardrailConfig, element: <GuardrailConfigTab /> },
    ],
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
  it('renders the Configuration tab from the detail endpoint', async () => {
    renderDetail('pii-filter');

    expect(
      await screen.findByText('pii-filter', undefined, { timeout: XL_SELECTOR_TIMEOUT })
    ).toBeInTheDocument();
    expect(screen.getByText('Blocks PII in user inputs and outputs')).toBeInTheDocument();
    // pii-filter has 2 models and 4 rail flows (2 input + 2 output).
    expect(screen.getAllByText('2').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('4').length).toBeGreaterThanOrEqual(1);
    // Structured config viewer renders the pipeline section.
    expect(screen.getByText('Pipeline')).toBeInTheDocument();
  });

  it('hides the draft actions until there are edits', async () => {
    renderDetail('pii-filter');
    await screen.findByText('pii-filter', undefined, { timeout: XL_SELECTOR_TIMEOUT });
    expect(screen.queryByRole('button', { name: 'Save Guardrail' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reset' })).not.toBeInTheDocument();
  });

  it('reveals Reset and Save Guardrail after editing, and Reset discards them', async () => {
    const user = userEvent.setup();
    renderDetail('pii-filter');
    await screen.findByText('pii-filter', undefined, { timeout: XL_SELECTOR_TIMEOUT });

    await user.type(screen.getByRole('textbox', { name: 'General instruction' }), 'Be concise.');

    expect(await screen.findByRole('button', { name: 'Save Guardrail' })).toBeInTheDocument();
    const reset = screen.getByRole('button', { name: 'Reset' });

    await user.click(reset);

    expect(screen.queryByRole('button', { name: 'Save Guardrail' })).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'General instruction' })).toHaveValue('');
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

  it('saves the draft and clears the draft actions', async () => {
    const user = userEvent.setup();
    renderDetail('pii-filter');
    await screen.findByText('pii-filter', undefined, { timeout: XL_SELECTOR_TIMEOUT });

    await user.type(screen.getByRole('textbox', { name: 'General instruction' }), 'Be concise.');
    await user.click(await screen.findByRole('button', { name: 'Save Guardrail' }));

    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Save Guardrail' })).not.toBeInTheDocument()
    );
  });
});
