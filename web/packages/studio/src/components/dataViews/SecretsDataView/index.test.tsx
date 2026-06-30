// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SecretsDataView } from '@studio/components/dataViews/SecretsDataView';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { server } from '@studio/mocks/node';
import { XL_SELECTOR_TIMEOUT } from '@studio/tests/util/constants';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router-dom';

const workspace = 'default';

const renderComponent = (props?: { emptyStateActions?: React.ReactNode }) => {
  return render(
    <MemoryRouter>
      <TestProviders>
        <SecretsDataView workspace={workspace} {...props} />
      </TestProviders>
    </MemoryRouter>
  );
};

describe('SecretsDataView', () => {
  describe('Data display', () => {
    it('displays secrets from the API', async () => {
      renderComponent();

      expect(
        await screen.findByText('openai-api-key', undefined, { timeout: XL_SELECTOR_TIMEOUT })
      ).toBeInTheDocument();

      expect(screen.getByText('anthropic-api-key')).toBeInTheDocument();
      expect(screen.getByText('huggingface-token')).toBeInTheDocument();
    });

    it('displays secret descriptions', async () => {
      renderComponent();

      expect(
        await screen.findByText('openai-api-key', undefined, { timeout: XL_SELECTOR_TIMEOUT })
      ).toBeInTheDocument();

      expect(screen.getByText('OpenAI API key for GPT-4 integration')).toBeInTheDocument();
    });

    it('displays search placeholder', async () => {
      renderComponent();

      expect(
        await screen.findByPlaceholderText('Search Secrets...', undefined, {
          timeout: XL_SELECTOR_TIMEOUT,
        })
      ).toBeInTheDocument();
    });
  });

  describe('Empty state', () => {
    it('displays empty state when no secrets exist', async () => {
      server.use(
        http.get(`${PLATFORM_BASE_URL}/apis/secrets/v2/workspaces/:workspace/secrets`, () =>
          HttpResponse.json({
            data: [],
            pagination: {
              page: 1,
              page_size: 25,
              current_page_size: 0,
              total_pages: 0,
              total_results: 0,
            },
          })
        )
      );

      renderComponent();

      expect(
        await screen.findByText('Manage Secrets', undefined, { timeout: XL_SELECTOR_TIMEOUT })
      ).toBeInTheDocument();

      expect(
        screen.getByText(
          'Start by creating a secret, refer to the documentation for formatting details.'
        )
      ).toBeInTheDocument();
      expect(screen.getByRole('link', { name: /Documentation/ })).toBeInTheDocument();
    });

    it('renders empty state actions when provided', async () => {
      server.use(
        http.get(`${PLATFORM_BASE_URL}/apis/secrets/v2/workspaces/:workspace/secrets`, () =>
          HttpResponse.json({
            data: [],
            pagination: {
              page: 1,
              page_size: 25,
              current_page_size: 0,
              total_pages: 0,
              total_results: 0,
            },
          })
        )
      );

      renderComponent({
        emptyStateActions: <button type="button">Create Secret</button>,
      });

      expect(
        await screen.findByText('Manage Secrets', undefined, { timeout: XL_SELECTOR_TIMEOUT })
      ).toBeInTheDocument();

      expect(screen.getByRole('button', { name: 'Create Secret' })).toBeInTheDocument();
    });
  });

  describe('Search', () => {
    it('filters secrets by name when searching', async () => {
      const user = userEvent.setup();
      renderComponent();

      expect(
        await screen.findByText('openai-api-key', undefined, { timeout: XL_SELECTOR_TIMEOUT })
      ).toBeInTheDocument();

      const searchInput = screen.getByPlaceholderText('Search Secrets...');
      await user.type(searchInput, 'openai');

      await waitFor(() => {
        expect(screen.queryByText('anthropic-api-key')).not.toBeInTheDocument();
        expect(screen.queryByText('huggingface-token')).not.toBeInTheDocument();
      });
    });

    it('shows no-results empty state when search has no matches', async () => {
      const user = userEvent.setup();
      renderComponent();

      expect(
        await screen.findByText('openai-api-key', undefined, { timeout: XL_SELECTOR_TIMEOUT })
      ).toBeInTheDocument();

      const searchInput = screen.getByPlaceholderText('Search Secrets...');
      await user.type(searchInput, 'nonexistent-secret-name');

      expect(
        await screen.findByText('No Results Found', undefined, { timeout: XL_SELECTOR_TIMEOUT })
      ).toBeInTheDocument();

      expect(screen.getByText('No secrets match your search')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Clear Search' })).toBeInTheDocument();
    });
  });
});
