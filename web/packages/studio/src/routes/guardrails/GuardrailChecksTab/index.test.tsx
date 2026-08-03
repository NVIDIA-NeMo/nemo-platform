// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { GUARDRAIL_CHECKS_ENTITY_TYPE } from '@studio/api/guardrail-checks/types';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { server } from '@studio/mocks/node';
import { GuardrailChecksTab } from '@studio/routes/guardrails/GuardrailChecksTab';
import {
  GUARDRAIL_CHECKS_DEFAULT_SUB_TAB,
  GuardrailChecksSubTab,
} from '@studio/routes/guardrails/GuardrailChecksTab/constants';
import { GuardrailConfigTab } from '@studio/routes/guardrails/GuardrailConfigTab';
import { GuardrailDetailRoute } from '@studio/routes/guardrails/GuardrailDetailRoute';
import { getGuardrailChecksRoute, getGuardrailChecksSubTabRoute } from '@studio/routes/utils';
import { XL_SELECTOR_TIMEOUT } from '@studio/tests/util/constants';
import { renderRoute, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Navigate, useLocation } from 'react-router';

const WORKSPACE = 'default';

const CHECKS_URL = `${PLATFORM_BASE_URL}/apis/entities/v2/workspaces/:workspace/entities/${GUARDRAIL_CHECKS_ENTITY_TYPE}`;

beforeEach(() => {
  localStorage.clear();
});

const LocationProbe = () => {
  const location = useLocation();
  return <div data-testid="checks-location">{location.pathname}</div>;
};

const routes = [
  {
    path: ROUTES.workspace.guardrailDetail,
    element: <GuardrailDetailRoute />,
    children: [
      { index: true, element: <Navigate to="config" replace /> },
      { path: ROUTES.workspace.guardrailConfig, element: <GuardrailConfigTab /> },
      {
        path: ROUTES.workspace.guardrailChecks,
        element: <Navigate to={GUARDRAIL_CHECKS_DEFAULT_SUB_TAB} replace />,
      },
      {
        path: ROUTES.workspace.guardrailChecksSubTab,
        element: (
          <>
            <GuardrailChecksTab />
            <LocationProbe />
          </>
        ),
      },
    ],
  },
  {
    path: ROUTES.workspace.guardrails,
    element: <div data-testid="guardrails-list">LIST</div>,
  },
];

const renderChecks = (name: string, history = getGuardrailChecksRoute(WORKSPACE, name)) =>
  renderRoute(undefined, { history, routes });

describe('GuardrailChecksTab', () => {
  it('renders the test cases editor when the config and checks both load', async () => {
    renderChecks('pii-filter');

    expect(
      await screen.findByText('Guardrail Test Cases', undefined, { timeout: XL_SELECTOR_TIMEOUT })
    ).toBeInTheDocument();
    expect(screen.getByText('Test 1')).toBeInTheDocument();
    expect(screen.getByText('Test 2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Run 2 Tests/ })).toBeInTheDocument();
  });

  it('redirects the bare checks URL onto the default sub-tab', async () => {
    renderChecks('pii-filter');

    await screen.findByText('Guardrail Test Cases', undefined, { timeout: XL_SELECTOR_TIMEOUT });
    expect(screen.getByTestId('checks-location')).toHaveTextContent(
      getGuardrailChecksSubTabRoute(WORKSPACE, 'pii-filter', GuardrailChecksSubTab.Tests)
    );
  });

  it('shows the summary and the results table on the Test Results sub-tab', async () => {
    const user = userEvent.setup();
    renderChecks('pii-filter');

    await screen.findByText('Guardrail Test Cases', undefined, { timeout: XL_SELECTOR_TIMEOUT });
    await user.click(screen.getByRole('tab', { name: 'Test Results' }));

    expect(
      await screen.findByText('Result Summary', undefined, { timeout: XL_SELECTOR_TIMEOUT })
    ).toBeInTheDocument();
    expect(screen.getByRole('row', { name: /My SSN is 123-45-6789/ })).toHaveTextContent('Guarded');
    expect(screen.getByRole('row', { name: /Hello there/ })).toHaveTextContent('Not run');
    expect(screen.getByTestId('checks-location')).toHaveTextContent(
      getGuardrailChecksSubTabRoute(WORKSPACE, 'pii-filter', GuardrailChecksSubTab.Results)
    );
  });

  it('restores the Test Results sub-tab when loaded straight from its URL', async () => {
    renderChecks(
      'pii-filter',
      getGuardrailChecksSubTabRoute(WORKSPACE, 'pii-filter', GuardrailChecksSubTab.Results)
    );

    expect(
      await screen.findByText('Result Summary', undefined, { timeout: XL_SELECTOR_TIMEOUT })
    ).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Test Results' })).toHaveAttribute(
      'aria-selected',
      'true'
    );
    expect(screen.queryByText('Add Another Test')).not.toBeInTheDocument();
  });

  it('shows an error state when the checks cannot be loaded', async () => {
    server.use(http.get(CHECKS_URL, () => new HttpResponse(null, { status: 500 })));

    renderChecks('pii-filter');

    expect(
      await screen.findByText('Failed to load guardrail tests.', undefined, {
        timeout: XL_SELECTOR_TIMEOUT,
      })
    ).toBeInTheDocument();
    expect(screen.queryByText('Guardrail Test Cases')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Run 0 Tests/ })).not.toBeInTheDocument();
  });

  it('shows the config error instead of the checks UI when the config cannot be loaded', async () => {
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
