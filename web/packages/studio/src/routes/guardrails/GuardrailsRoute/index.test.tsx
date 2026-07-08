// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ROUTES } from '@studio/constants/routes';
import { GuardrailsRoute } from '@studio/routes/guardrails/GuardrailsRoute';
import { getGuardrailDetailRoute, getGuardrailsRoute } from '@studio/routes/utils';
import { XL_SELECTOR_TIMEOUT } from '@studio/tests/util/constants';
import { renderRoute, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';
import { useLocation } from 'react-router-dom';

const WORKSPACE = 'default';

const LocationProbe = () => {
  const location = useLocation();
  return <div data-testid="detail-location">{location.pathname}</div>;
};

const renderList = () =>
  renderRoute(undefined, {
    history: getGuardrailsRoute(WORKSPACE),
    routes: [
      {
        path: ROUTES.workspace.guardrails,
        element: <GuardrailsRoute />,
      },
      {
        path: ROUTES.workspace.guardrailDetail,
        element: <LocationProbe />,
      },
    ],
  });

describe('GuardrailsRoute', () => {
  it('navigates to the detail route when a row is clicked', async () => {
    const user = userEvent.setup();
    renderList();

    const row = await screen.findByText('pii-filter', undefined, { timeout: XL_SELECTOR_TIMEOUT });
    await user.click(row);

    expect(await screen.findByTestId('detail-location')).toHaveTextContent(
      getGuardrailDetailRoute(WORKSPACE, 'pii-filter')
    );
  });
});
