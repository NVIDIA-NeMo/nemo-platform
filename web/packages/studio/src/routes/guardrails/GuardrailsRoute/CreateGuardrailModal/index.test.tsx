// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { server } from '@studio/mocks/node';
import { CreateGuardrailModal } from '@studio/routes/guardrails/GuardrailsRoute/CreateGuardrailModal';
import { mockUseNavigate, mockUseParams } from '@studio/tests/util/mockUseParams';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { BrowserRouter } from 'react-router';
import type { Mock } from 'vitest';

const WORKSPACE = 'test-workspace';
const CONFIGS_URL = `${PLATFORM_BASE_URL}/apis/guardrails/v2/workspaces/:workspace/configs`;

const renderModal = (onClose = vi.fn()) => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <CreateGuardrailModal open onClose={onClose} />
      </BrowserRouter>
    </QueryClientProvider>
  );
  return { onClose };
};

describe('CreateGuardrailModal', () => {
  let navigate: Mock;

  beforeEach(() => {
    mockUseParams({ [ROUTE_PARAMS.workspace]: WORKSPACE });
    navigate = vi.fn();
    mockUseNavigate(navigate);
  });

  it('creates the guardrail and navigates to its detail page', async () => {
    server.use(
      http.post(CONFIGS_URL, () => HttpResponse.json({ name: 'my-rail' }, { status: 201 }))
    );
    const user = userEvent.setup();
    const { onClose } = renderModal();

    await user.type(screen.getByRole('textbox'), 'my-rail');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      expect(navigate).toHaveBeenCalledWith(`/workspaces/${WORKSPACE}/guardrails/my-rail`);
    });
    expect(onClose).toHaveBeenCalled();
  });

  it('keeps the modal open and does not navigate when creation fails', async () => {
    server.use(
      http.post(CONFIGS_URL, () =>
        HttpResponse.json({ detail: 'Name already in use' }, { status: 409 })
      )
    );
    const user = userEvent.setup();
    const { onClose } = renderModal();

    await user.type(screen.getByRole('textbox'), 'my-rail');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      expect(screen.getByText('Name already in use')).toBeInTheDocument();
    });
    expect(navigate).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('rejects a name that does not match the entity name pattern', async () => {
    const user = userEvent.setup();
    renderModal();

    await user.type(screen.getByRole('textbox'), 'Not Valid');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Create' })).toBeDisabled();
    });
  });
});
