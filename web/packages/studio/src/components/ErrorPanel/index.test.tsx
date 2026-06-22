// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { suppressConsoleError } from '@nemo/testing/utils/suppress-console';
import { ErrorPanel, ErrorPanelProps } from '@studio/components/ErrorPanel';
import { mockUseNavigate } from '@studio/tests/util/mockUseParams';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

// React error boundaries always call console.error when catching errors.
// This is expected React internals behavior, not a bug in our code.
// Also suppresses: React Router error boundary messages, and WebsiteLogger.error(undefined)
// where undefined comes from JSON.stringify(errorMessage) when errorMessage prop is not provided.
beforeEach(() => {
  suppressConsoleError(
    'The above error occurred in',
    'React Router caught the following error',
    'undefined'
  );
});

// Helper to render the error component within a router context that has an error
const renderWithRouterError = (
  props: ErrorPanelProps,
  error: Error | { status: number; statusText: string; data?: unknown }
) => {
  // Create a route that throws the error
  const ThrowingComponent = () => {
    if (error instanceof Error) {
      throw error;
    }
    // For route error responses, we need to throw a Response
    throw new Response(JSON.stringify(error.data), {
      status: error.status,
      statusText: error.statusText,
    });
  };

  const router = createMemoryRouter(
    [
      {
        path: '/',
        element: <ThrowingComponent />,
        errorElement: <ErrorPanel {...props} />,
      },
    ],
    { initialEntries: ['/'] }
  );

  return render(<RouterProvider router={router} />);
};

describe('ErrorPanel', () => {
  describe('Error Display', () => {
    it('displays error UI when an error occurs', () => {
      renderWithRouterError({ title: 'Evaluator' }, new Error('Test error'));

      expect(screen.getByTestId('error-panel')).toBeInTheDocument();
    });

    it('displays the correct title', () => {
      renderWithRouterError({ title: 'Evaluator' }, new Error('Test error'));

      expect(screen.getByText('Evaluator')).toBeInTheDocument();
    });

    it('displays error icon', () => {
      renderWithRouterError({ title: 'Customizer' }, new Error('Test error'));

      expect(screen.getByTestId('nv-status-message-media')).toBeInTheDocument();
    });

    it('displays the error message', () => {
      renderWithRouterError({ title: 'Evaluator' }, new Error('Test error message'));

      expect(screen.getByText('Test error message')).toBeInTheDocument();
    });

    it('displays custom title', () => {
      renderWithRouterError({ title: 'Custom Title' }, new Error('Test error'));

      expect(screen.getByText('Custom Title')).toBeInTheDocument();
    });
  });

  describe('User Actions', () => {
    it('renders Go Back button', () => {
      renderWithRouterError({ title: 'Evaluator' }, new Error('Test error'));

      expect(screen.getByRole('button', { name: 'Go Back' })).toBeInTheDocument();
    });

    it('renders Refresh Page button', () => {
      renderWithRouterError({ title: 'Evaluator' }, new Error('Test error'));

      expect(screen.getByRole('button', { name: 'Refresh Page' })).toBeInTheDocument();
    });

    it('calls navigate(-1) when Go Back is clicked', async () => {
      const user = userEvent.setup();
      const navigateSpy = vi.fn();
      mockUseNavigate(navigateSpy);

      renderWithRouterError({ title: 'Evaluator' }, new Error('Test error'));

      await user.click(screen.getByRole('button', { name: 'Go Back' }));

      expect(navigateSpy).toHaveBeenCalledWith(-1);
    });

    it('calls window.location.reload when Refresh Page is clicked', () => {
      const reloadSpy = vi.fn();
      Object.defineProperty(window, 'location', {
        value: { reload: reloadSpy },
        writable: true,
      });

      renderWithRouterError({ title: 'Evaluator' }, new Error('Test error'));

      fireEvent.click(screen.getByRole('button', { name: 'Refresh Page' }));

      expect(reloadSpy).toHaveBeenCalledTimes(1);
    });
  });

  describe('Route Error Responses', () => {
    it('handles route errors', () => {
      renderWithRouterError(
        { title: 'Evaluator' },
        {
          status: 500,
          statusText: 'Internal Server Error',
        }
      );

      expect(screen.getByText('Error')).toBeInTheDocument();
    });
  });
});
