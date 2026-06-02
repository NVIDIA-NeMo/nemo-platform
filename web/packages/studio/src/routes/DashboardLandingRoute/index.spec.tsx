// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ROUTES } from '@studio/constants/routes';
import { DashboardLandingRoute } from '@studio/routes/DashboardLandingRoute';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, generatePath, RouterProvider } from 'react-router';

const workspace = 'default';

const renderRoute = () => {
  const route = generatePath(ROUTES.workspace.dashboard, { workspace });
  const router = createMemoryRouter(
    [{ path: ROUTES.workspace.dashboard, element: <DashboardLandingRoute /> }],
    {
      initialEntries: [route],
    }
  );

  return render(
    <TestProviders>
      <RouterProvider router={router} />
    </TestProviders>
  );
};

describe('DashboardLandingRoute', () => {
  it('renders the dashboard landing page', async () => {
    renderRoute();

    expect(await screen.findByText('What would you like to do?')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Message Claude' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Explore repo/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Draft a change/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Review recent work/ })).toBeInTheDocument();
  });

  it('lets prompt suggestions populate the landing composer', async () => {
    const user = userEvent.setup();
    renderRoute();

    await user.click(await screen.findByRole('button', { name: /Explore repo/ }));

    expect(screen.getByRole('textbox', { name: 'Message Claude' })).toHaveValue(
      'Give me a concise map of this repo and the main places I should know about.'
    );
  });

  it('only enables the send affordance once the composer has text', async () => {
    const user = userEvent.setup();
    renderRoute();

    const composer = await screen.findByRole('textbox', { name: 'Message Claude' });
    const sendButton = screen.getByRole('button', { name: 'Send message' });

    expect(sendButton).toBeDisabled();

    await user.type(composer, 'Sketch a dashboard');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Send message' })).toBeEnabled();
    });
  });
});
