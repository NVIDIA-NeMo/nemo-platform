// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { renderRoute, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';

describe('ErrorBoundary', () => {
  it('Navigates to previous page when clicking Go Back button', async () => {
    const user = userEvent.setup();

    renderRoute(undefined, {
      routes: [
        { path: '/some-page', element: <h1>Previous page</h1> },
        { path: '/hypermodels', element: <ErrorMessage /> },
      ],
      history: ['/some-page', '/hypermodels'],
    });

    const backButton = screen.getByRole('button', { name: /Go back/i });
    await user.click(backButton);

    // Expect that we've navigated back to the previous page
    expect(screen.getByText(/Previous page/i)).toBeInTheDocument();
  });
});
