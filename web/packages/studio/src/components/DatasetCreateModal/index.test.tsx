// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { MockToastProvider } from '@nemo/common/src/tests/MockToastProvider';
import type { FilesetOutput as Dataset } from '@nemo/sdk/generated/platform/schema';
import { DatasetCreateModal } from '@studio/components/DatasetCreateModal';
import { DatasetCreateModalMode } from '@studio/components/DatasetCreateModal/constants';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { server } from '@studio/mocks/node';
import { mockUseNavigate, mockUseParams } from '@studio/tests/util/mockUseParams';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { BrowserRouter } from 'react-router-dom';

vi.mock('@studio/api/datasets/useDatasetCreate', () => ({
  useDatasetCreate: () => ({
    mutateAsync: vi.fn(),
    error: null,
    isPending: false,
    reset: vi.fn(),
  }),
}));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
});

describe('DatasetCreateModal', () => {
  beforeEach(() => {
    mockUseParams({
      [ROUTE_PARAMS.workspace]: 'test-workspace',
    });
    mockUseNavigate();
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <MockToastProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>{children}</BrowserRouter>
      </QueryClientProvider>
    </MockToastProvider>
  );

  it('should transform spaces to dashes in dataset name field as user types', async () => {
    const user = userEvent.setup();
    render(
      <Wrapper>
        <DatasetCreateModal open onClose={vi.fn()} />
      </Wrapper>
    );

    const nameInput = screen.getByPlaceholderText('Name this dataset') as HTMLInputElement;

    await user.type(nameInput, 'my dataset name');

    expect(nameInput.value).toBe('my-dataset-name');
  });

  describe('Edit mode', () => {
    it('should not allow name editing in edit mode', async () => {
      render(
        <Wrapper>
          <DatasetCreateModal open onClose={vi.fn()} mode={DatasetCreateModalMode.Edit} />
        </Wrapper>
      );
      const nameInput = screen.getByPlaceholderText('Name this dataset') as HTMLInputElement;
      expect(nameInput).toBeDisabled();
    });

    it('should autofill the form fields in edit mode', async () => {
      const dataset: Dataset = {
        id: 'test-id',
        name: 'test-dataset',
        workspace: 'default',
        description: 'test-description',
        purpose: 'dataset',
        storage: { type: 'local', path: '/data' } as const,
        metadata: {},
        custom_fields: {},
        project: 'default',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      };
      render(
        <Wrapper>
          <DatasetCreateModal
            open
            onClose={vi.fn()}
            mode={DatasetCreateModalMode.Edit}
            dataset={dataset}
          />
        </Wrapper>
      );
      await waitFor(() =>
        expect(screen.getByPlaceholderText('Name this dataset')).toHaveValue(dataset.name)
      );
      await waitFor(() =>
        expect(
          screen.getByPlaceholderText('Provide a useful description for this dataset')
        ).toHaveValue(dataset.description)
      );
    });

    it('should send PATCH with updated description when form is submitted', async () => {
      const user = userEvent.setup();
      const dataset: Dataset = {
        id: 'test-id',
        name: 'test-dataset',
        workspace: 'test-workspace',
        description: 'Original description',
        purpose: 'dataset',
        storage: { type: 'local', path: '/data' } as const,
        metadata: {},
        custom_fields: {},
        project: 'test-project',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      };

      let capturedBody: Record<string, unknown> | undefined;
      server.use(
        http.patch(
          `${PLATFORM_BASE_URL}/apis/files/v2/workspaces/:workspace/filesets/:name`,
          async ({ request, params }) => {
            capturedBody = (await request.json()) as Record<string, unknown>;
            return HttpResponse.json({
              ...dataset,
              description: capturedBody.description,
              workspace: params.workspace as string,
              name: params.name as string,
              updated_at: new Date().toISOString(),
            });
          }
        )
      );

      const onClose = vi.fn();

      render(
        <Wrapper>
          <DatasetCreateModal
            open
            onClose={onClose}
            mode={DatasetCreateModalMode.Edit}
            dataset={dataset}
          />
        </Wrapper>
      );

      const descriptionInput = await screen.findByPlaceholderText(
        'Provide a useful description for this dataset'
      );

      await user.clear(descriptionInput);
      await user.type(descriptionInput, 'Updated description');

      const saveButton = screen.getByRole('button', { name: /save/i });
      await user.click(saveButton);

      await waitFor(() => {
        expect(capturedBody).toEqual({ description: 'Updated description' });
      });

      await waitFor(() => {
        expect(onClose).toHaveBeenCalled();
      });
    });
  });
});
