// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { GUARDRAIL_CHECKS_ENTITY_TYPE } from '@studio/api/guardrail-checks/types';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { server } from '@studio/mocks/node';
import { GuardrailChecksTab } from '@studio/routes/guardrails/GuardrailChecksTab';
import { GuardrailConfigTab } from '@studio/routes/guardrails/GuardrailConfigTab';
import { GuardrailDetailRoute } from '@studio/routes/guardrails/GuardrailDetailRoute';
import { getGuardrailChecksRoute } from '@studio/routes/utils';
import { XL_SELECTOR_TIMEOUT } from '@studio/tests/util/constants';
import { renderRoute, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Navigate } from 'react-router-dom';

const WORKSPACE = 'default';

const CHECKS_URL = `${PLATFORM_BASE_URL}/apis/entities/v2/workspaces/:workspace/entities/${GUARDRAIL_CHECKS_ENTITY_TYPE}`;

beforeEach(() => {
  localStorage.clear();
});

// The tab only ever renders under GuardrailDetailRoute, so exercise it through the real parent —
// that is what decides whether a config failure ever reaches the tab at all.
const routes = [
  {
    path: ROUTES.workspace.guardrailDetail,
    element: <GuardrailDetailRoute />,
    children: [
      { index: true, element: <Navigate to="config" replace /> },
      { path: ROUTES.workspace.guardrailConfig, element: <GuardrailConfigTab /> },
      { path: ROUTES.workspace.guardrailChecks, element: <GuardrailChecksTab /> },
    ],
  },
  {
    path: ROUTES.workspace.guardrails,
    element: <div data-testid="guardrails-list">LIST</div>,
  },
];

const renderChecks = (name: string) =>
  renderRoute(undefined, {
    history: getGuardrailChecksRoute(WORKSPACE, name),
    routes,
  });

describe('GuardrailChecksTab', () => {
  it('renders the test cases editor when the config and checks both load', async () => {
    renderChecks('pii-filter');

    expect(
      await screen.findByText('Guardrail Test Cases', undefined, { timeout: XL_SELECTOR_TIMEOUT })
    ).toBeInTheDocument();
    // One card per check in the mock page, and the batch-run button reflects the same count.
    expect(screen.getByText('Test 1')).toBeInTheDocument();
    expect(screen.getByText('Test 2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Run 2 Tests/ })).toBeInTheDocument();
  });

  it('shows the summary and the results table on the Test Results sub-tab', async () => {
    const user = userEvent.setup();
    renderChecks('pii-filter');

    await screen.findByText('Guardrail Test Cases', undefined, { timeout: XL_SELECTOR_TIMEOUT });
    await user.click(screen.getByRole('tab', { name: 'Test Results' }));

    expect(
      await screen.findByText('Result Summary', undefined, { timeout: XL_SELECTOR_TIMEOUT })
    ).toBeInTheDocument();
    // Both mock checks appear, each carrying its own verdict: chk-1 ran and was blocked, chk-2
    // has never run.
    expect(screen.getByRole('row', { name: /My SSN is 123-45-6789/ })).toHaveTextContent('Guarded');
    expect(screen.getByRole('row', { name: /Hello there/ })).toHaveTextContent('Not run');
  });

  it('shows an error state when the checks cannot be loaded', async () => {
    server.use(http.get(CHECKS_URL, () => new HttpResponse(null, { status: 500 })));

    renderChecks('pii-filter');

    expect(
      await screen.findByText('Failed to load guardrail tests.', undefined, {
        timeout: XL_SELECTOR_TIMEOUT,
      })
    ).toBeInTheDocument();
    // A failed fetch must not degrade into an empty editor — that reads as "this config has no
    // test cases", which is how a user ends up recreating checks they still have.
    expect(screen.queryByText('Guardrail Test Cases')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Run 0 Tests/ })).not.toBeInTheDocument();
  });

  it('shows the config error instead of the checks UI when the config cannot be loaded', async () => {
    // The default configs handler 404s unknown names; the parent route owns this error state and
    // never renders the tab, so the tab must not paint a competing error of its own.
    renderChecks('does-not-exist');

    expect(
      await screen.findByText('Failed to load guardrail config.', undefined, {
        timeout: XL_SELECTOR_TIMEOUT,
      })
    ).toBeInTheDocument();
    expect(screen.queryByText('Guardrail Test Cases')).not.toBeInTheDocument();
    expect(screen.queryByText('Failed to load guardrail tests.')).not.toBeInTheDocument();
  });
});
