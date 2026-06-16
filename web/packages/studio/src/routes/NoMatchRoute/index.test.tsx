// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { NoMatchRoute } from '@studio/routes/NoMatchRoute';
import { LOCATION_DISPLAY_TEST_ID } from '@studio/tests/util/constants';
import { LocationDisplay } from '@studio/tests/util/LocationDisplay';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router';

const renderRoute = () => {
  const router = createMemoryRouter(
    [
      {
        path: '/',
        element: <LocationDisplay />,
      },
      {
        path: '*',
        element: <NoMatchRoute />,
      },
    ],
    {
      initialEntries: ['/', '/unknown-404'],
    }
  );
  return render(
    <TestProviders>
      <RouterProvider router={router} />
    </TestProviders>
  );
};
describe('NoMatchRoute', () => {
  it('renders with navigation', async () => {
    renderRoute();
    await screen.findByText('404 Error');
    expect(screen.getByText("Even AI can't find this page!")).toBeInTheDocument();
    expect(
      screen.getByText(
        "If you're logged in, this might be a permissions issue. Check with your Org or Team Admin. Otherwise, you can return to your previous screen by clicking the link below."
      )
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Go Back' })).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Go Back' }));
    expect(await screen.findByTestId(LOCATION_DISPLAY_TEST_ID)).toHaveTextContent('/');
  });
});
