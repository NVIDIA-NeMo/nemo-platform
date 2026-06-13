// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { GuardrailConfig } from '@nemo/sdk/generated/platform/schema';
import { GuardrailsDataView } from '@studio/components/dataViews/GuardrailsDataView';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { server } from '@studio/mocks/node';
import { XL_SELECTOR_TIMEOUT } from '@studio/tests/util/constants';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

const workspace = 'default';

const findPiiFilterRow = async () => {
  return await screen.findByText('pii-filter', undefined, { timeout: XL_SELECTOR_TIMEOUT });
};

const renderComponent = (
  props: {
    onRowClick?: (config: GuardrailConfig) => void;
    onRequestDelete?: (config: GuardrailConfig) => void;
  } = {}
) => {
  const router = createMemoryRouter([
    {
      path: '/',
      element: (
        <GuardrailsDataView
          workspace={workspace}
          onRowClick={props.onRowClick ?? vi.fn()}
          onRequestDelete={props.onRequestDelete}
        />
      ),
    },
  ]);

  return render(
    <TestProviders>
      <RouterProvider router={router} />
    </TestProviders>
  );
};

describe.skip('GuardrailsDataView', () => {
  it('renders config names from the API', async () => {
    renderComponent();
    expect(await findPiiFilterRow()).toBeInTheDocument();
    expect(screen.getByText('toxicity-guard')).toBeInTheDocument();
  });

  it('renders descriptions', async () => {
    renderComponent();
    await findPiiFilterRow();
    expect(screen.getByText('Blocks PII in user inputs and outputs')).toBeInTheDocument();
  });

  it('renders model count column', async () => {
    renderComponent();
    await findPiiFilterRow();
    // pii-filter has 2 models, toxicity-guard has 1
    const modelCells = screen.getAllByText('2');
    expect(modelCells.length).toBeGreaterThanOrEqual(1);
  });

  it('renders rail count column', async () => {
    renderComponent();
    await findPiiFilterRow();
    // pii-filter has 4 rail flows (2 input + 2 output)
    const railCells = screen.getAllByText('4');
    expect(railCells.length).toBeGreaterThanOrEqual(1);
  });

  it('calls onRowClick when a row is clicked', async () => {
    const user = userEvent.setup();
    const onRowClick = vi.fn();
    renderComponent({ onRowClick });
    const row = await findPiiFilterRow();
    await user.click(row);
    expect(onRowClick).toHaveBeenCalledWith(expect.objectContaining({ name: 'pii-filter' }));
  });

  it('shows empty state when there are no configs', async () => {
    server.use(
      http.get(`${PLATFORM_BASE_URL}/apis/guardrails/v2/workspaces/:workspace/configs`, () =>
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
      await screen.findByText('Manage Guardrail Configs', undefined, {
        timeout: XL_SELECTOR_TIMEOUT,
      })
    ).toBeInTheDocument();
  });

  it('calls onRequestDelete when the Delete row action is selected', async () => {
    const user = userEvent.setup();
    const onRequestDelete = vi.fn();
    renderComponent({ onRequestDelete });
    await findPiiFilterRow();

    const menuButtons = screen.getAllByRole('button', { name: /actions/i });
    await user.click(menuButtons[0]);
    await user.click(await screen.findByRole('menuitem', { name: 'Delete' }));
    await waitFor(() => {
      expect(onRequestDelete).toHaveBeenCalledWith(expect.objectContaining({ name: 'pii-filter' }));
    });
  });

  it('shows error state when the API request fails', async () => {
    server.use(
      http.get(`${PLATFORM_BASE_URL}/apis/guardrails/v2/workspaces/:workspace/configs`, () =>
        HttpResponse.error()
      )
    );
    renderComponent();
    expect(
      await screen.findByTestId('error-panel', undefined, { timeout: XL_SELECTOR_TIMEOUT })
    ).toBeInTheDocument();
  });
});
