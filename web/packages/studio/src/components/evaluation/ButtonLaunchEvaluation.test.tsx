// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DEFAULT_WORKSPACE } from '@nemo/common/src/models/constants';
import { ButtonLaunchEvaluation } from '@studio/components/evaluation/ButtonLaunchEvaluation';
import { ROUTE_PARAMS, ROUTES } from '@studio/constants/routes';
import { getEvaluationResultsRoute } from '@studio/routes/utils';
import { LOCATION_DISPLAY_TEST_ID } from '@studio/tests/util/constants';
import { LocationDisplay } from '@studio/tests/util/LocationDisplay';
import { mockUseParams } from '@studio/tests/util/mockUseParams';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

const renderRoute = () => {
  const router = createMemoryRouter(
    [
      { path: ROUTES.workspace.index, element: <ButtonLaunchEvaluation /> },
      { path: getEvaluationResultsRoute(DEFAULT_WORKSPACE), element: <LocationDisplay /> },
    ],
    { initialEntries: [ROUTES.workspace.index] }
  );
  return render(
    <TestProviders>
      <RouterProvider router={router} />
    </TestProviders>
  );
};

describe('ButtonLaunchEvaluation', () => {
  beforeEach(() => {
    mockUseParams({ [ROUTE_PARAMS.workspace]: DEFAULT_WORKSPACE });
  });

  it('should render the button with correct text', async () => {
    renderRoute();
    expect(await screen.findByText('Launch Evaluation')).toBeInTheDocument();
    expect(screen.getByRole('button')).toBeInTheDocument();
  });

  it('should navigate to evaluation results when clicked', async () => {
    const user = userEvent.setup();
    renderRoute();

    await user.click(await screen.findByText('Launch Evaluation'));

    const locationElement = await screen.findByTestId(LOCATION_DISPLAY_TEST_ID);
    expect(locationElement).toHaveTextContent(getEvaluationResultsRoute(DEFAULT_WORKSPACE));
  });

  it('should pass through additional props', async () => {
    const router = createMemoryRouter(
      [{ path: ROUTES.workspace.index, element: <ButtonLaunchEvaluation disabled /> }],
      { initialEntries: [ROUTES.workspace.index] }
    );
    render(
      <TestProviders>
        <RouterProvider router={router} />
      </TestProviders>
    );
    expect(await screen.findByRole('button')).toBeDisabled();
  });
});
