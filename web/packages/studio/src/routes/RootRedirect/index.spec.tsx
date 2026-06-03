// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ROUTES } from '@studio/constants/routes';
import { LOCATION_DISPLAY_TEST_ID } from '@studio/tests/util/constants';
import { LocationDisplay } from '@studio/tests/util/LocationDisplay';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';

const renderRootRedirect = async (initialPath = '/') => {
  const { RootRedirect } = await import('@studio/routes/RootRedirect');
  const router = createMemoryRouter(
    [
      {
        path: '/',
        element: <RootRedirect />,
      },
      {
        path: '/workspaces',
        element: <RootRedirect />,
      },
      {
        path: ROUTES.workspace.dashboard,
        element: <LocationDisplay />,
      },
      {
        path: ROUTES.workspace.agentsList,
        element: <LocationDisplay />,
      },
      {
        path: ROUTES.workspace.index,
        element: <LocationDisplay />,
      },
    ],
    { initialEntries: [initialPath] }
  );

  return render(
    <TestProviders>
      <RouterProvider router={router} />
    </TestProviders>
  );
};

describe('RootRedirect', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('uses coding agent studio as the root landing page when enabled', async () => {
    vi.resetModules();
    vi.stubEnv('VITE_FF_CODING_AGENT_STUDIO_ENABLED', 'true');

    await renderRootRedirect();

    const location = await screen.findByTestId(LOCATION_DISPLAY_TEST_ID);
    expect(location).toHaveTextContent('/workspaces/');
    expect(location).toHaveTextContent('/dashboard');
  });

  it('uses the dashboard route as the /workspaces landing page when coding agent studio is enabled', async () => {
    vi.resetModules();
    vi.stubEnv('VITE_FF_CODING_AGENT_STUDIO_ENABLED', 'true');
    await renderRootRedirect('/workspaces');

    const location = await screen.findByTestId(LOCATION_DISPLAY_TEST_ID);
    expect(location).toHaveTextContent('/workspaces/');
    expect(location).toHaveTextContent('/dashboard');
  });
});
