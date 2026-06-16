// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import {
  bulkDeleteTestDatasets,
  datasetWithUndefinedNamespace,
  datasetWithUndefinedName,
} from '@studio/mocks/datasets';
import { server } from '@studio/mocks/node';
import { DatasetBulkDeleteModal } from '@studio/routes/FilesetListRoute/DatasetBulkDeleteModal';
import { render } from '@studio/tests/util/render';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

// Mock the useWorkspaceFromPath hook to provide the required project context
vi.mock('@studio/hooks/useWorkspaceFromPath', () => ({
  useWorkspaceFromPath: () => 'test-workspace',
}));

describe('DatasetBulkDeleteModal', () => {
  const mockOnConfirmSuccess = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('renders the delete trigger button', () => {
      render(
        <DatasetBulkDeleteModal
          selectedDatasets={bulkDeleteTestDatasets}
          onConfirmSuccess={mockOnConfirmSuccess}
        />
      );

      const triggerButton = screen.getByTestId('bulk-delete-modal-trigger-button');
      expect(triggerButton).toBeInTheDocument();
    });

    it('displays correct dataset count in singular form', () => {
      render(
        <DatasetBulkDeleteModal
          selectedDatasets={[bulkDeleteTestDatasets[0]]}
          onConfirmSuccess={mockOnConfirmSuccess}
        />
      );

      const triggerButton = screen.getByTestId('bulk-delete-modal-trigger-button');
      expect(triggerButton).toBeInTheDocument();
    });

    it('displays correct dataset count in plural form', () => {
      render(
        <DatasetBulkDeleteModal
          selectedDatasets={bulkDeleteTestDatasets}
          onConfirmSuccess={mockOnConfirmSuccess}
        />
      );

      const triggerButton = screen.getByTestId('bulk-delete-modal-trigger-button');
      expect(triggerButton).toBeInTheDocument();
    });

    it('renders with empty dataset array', () => {
      render(
        <DatasetBulkDeleteModal selectedDatasets={[]} onConfirmSuccess={mockOnConfirmSuccess} />
      );

      const triggerButton = screen.getByTestId('bulk-delete-modal-trigger-button');
      expect(triggerButton).toBeInTheDocument();
    });
  });

  describe('Modal Interactions', () => {
    it('opens modal when trigger button is clicked', async () => {
      const user = userEvent.setup();

      render(
        <DatasetBulkDeleteModal
          selectedDatasets={bulkDeleteTestDatasets}
          onConfirmSuccess={mockOnConfirmSuccess}
        />
      );

      const triggerButton = screen.getByTestId('bulk-delete-modal-trigger-button');
      await user.click(triggerButton);

      // Check if modal is open by looking for modal content
      expect(await screen.findByRole('dialog')).toBeInTheDocument();

      // Check modal heading
      expect(screen.getByText(/Delete 3 Datasets/)).toBeInTheDocument();

      // Check modal content
      expect(screen.getByText('Are you sure you want to delete this?')).toBeInTheDocument();
    });

    it('displays singular form in modal heading for single dataset', async () => {
      const user = userEvent.setup();

      render(
        <DatasetBulkDeleteModal
          selectedDatasets={[bulkDeleteTestDatasets[0]]}
          onConfirmSuccess={mockOnConfirmSuccess}
        />
      );

      const triggerButton = screen.getByTestId('bulk-delete-modal-trigger-button');
      await user.click(triggerButton);

      expect(await screen.findByText(/Delete 1 Dataset$/)).toBeInTheDocument();
    });

    it('closes modal when cancel button is clicked', async () => {
      const user = userEvent.setup();

      render(
        <DatasetBulkDeleteModal
          selectedDatasets={bulkDeleteTestDatasets}
          onConfirmSuccess={mockOnConfirmSuccess}
        />
      );

      // Open modal
      const triggerButton = screen.getByTestId('bulk-delete-modal-trigger-button');
      await user.click(triggerButton);

      expect(await screen.findByRole('dialog')).toBeInTheDocument();

      // Click cancel
      const cancelButton = screen.getByRole('button', { name: /cancel/i });
      await user.click(cancelButton);

      // Modal should be closed
      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      });
    });
  });

  describe('Delete Operations', () => {
    it('calls delete for each selected dataset when delete button is clicked', async () => {
      const user = userEvent.setup();
      const deleteRequests: Array<{ workspace: string; name: string }> = [];

      // Track delete requests
      server.use(
        http.delete(
          `${PLATFORM_BASE_URL}/apis/files/v2/workspaces/:workspace/filesets/:name`,
          ({ params }) => {
            deleteRequests.push({
              workspace: params.workspace as string,
              name: params.name as string,
            });
            return new HttpResponse(null, { status: 200 });
          }
        )
      );

      render(
        <DatasetBulkDeleteModal
          selectedDatasets={bulkDeleteTestDatasets}
          onConfirmSuccess={mockOnConfirmSuccess}
        />
      );

      // Open modal
      const triggerButton = screen.getByTestId('bulk-delete-modal-trigger-button');
      await user.click(triggerButton);

      expect(await screen.findByRole('dialog')).toBeInTheDocument();

      // Click delete
      const deleteButton = within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Delete',
      });
      await user.click(deleteButton);

      // Wait for all delete requests to complete
      await waitFor(() => {
        expect(deleteRequests).toHaveLength(3);
      });

      // Verify correct delete requests were made
      expect(deleteRequests).toContainEqual({
        workspace: 'test-namespace',
        name: 'dataset-1',
      });
      expect(deleteRequests).toContainEqual({
        workspace: 'test-namespace',
        name: 'dataset-2',
      });
      expect(deleteRequests).toContainEqual({
        workspace: 'test-namespace',
        name: 'dataset-3',
      });
    });

    it('calls onConfirmSuccess and closes modal after successful deletion', async () => {
      const user = userEvent.setup();

      render(
        <DatasetBulkDeleteModal
          selectedDatasets={bulkDeleteTestDatasets}
          onConfirmSuccess={mockOnConfirmSuccess}
        />
      );

      // Open modal
      const triggerButton = screen.getByTestId('bulk-delete-modal-trigger-button');
      await user.click(triggerButton);

      expect(await screen.findByRole('dialog')).toBeInTheDocument();

      // Click delete
      const deleteButton = within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Delete',
      });
      await user.click(deleteButton);

      // Wait for deletion to complete and success callback
      await waitFor(() => {
        expect(mockOnConfirmSuccess).toHaveBeenCalledTimes(1);
      });

      // Modal should be closed
      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      });
    });

    it('handles deletion errors gracefully', async () => {
      const user = userEvent.setup();
      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      // Override with error response
      server.use(
        http.delete(
          `${PLATFORM_BASE_URL}/apis/files/v2/workspaces/:workspace/filesets/:name`,
          () => new HttpResponse(null, { status: 500 })
        )
      );

      render(
        <DatasetBulkDeleteModal
          selectedDatasets={[bulkDeleteTestDatasets[0]]}
          onConfirmSuccess={mockOnConfirmSuccess}
        />
      );

      // Open modal
      const triggerButton = screen.getByTestId('bulk-delete-modal-trigger-button');
      await user.click(triggerButton);

      expect(await screen.findByRole('dialog')).toBeInTheDocument();

      // Click delete
      const deleteButton = within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Delete',
      });
      await user.click(deleteButton);

      // Wait for error handling
      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          'Failed to delete datasets',
          expect.any(Error)
        );
      });

      // onConfirmSuccess should not be called on error
      expect(mockOnConfirmSuccess).not.toHaveBeenCalled();

      consoleErrorSpy.mockRestore();
    });

    it('shows loading state during deletion', async () => {
      const user = userEvent.setup();

      // Use a deferred promise so the test controls when the deletion resolves.
      // This avoids a race where the mutation completes before the assertion runs.
      let resolveDelete!: () => void;
      const deleteGate = new Promise<void>((r) => {
        resolveDelete = r;
      });

      server.use(
        http.delete(
          `${PLATFORM_BASE_URL}/apis/files/v2/workspaces/:workspace/filesets/:name`,
          async () => {
            await deleteGate;
            return new HttpResponse(null, { status: 200 });
          }
        )
      );

      render(
        <DatasetBulkDeleteModal
          selectedDatasets={bulkDeleteTestDatasets}
          onConfirmSuccess={mockOnConfirmSuccess}
        />
      );

      // Open modal
      const triggerButton = screen.getByTestId('bulk-delete-modal-trigger-button');
      await user.click(triggerButton);

      expect(await screen.findByRole('dialog')).toBeInTheDocument();

      // Click delete
      const deleteButton = within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Delete',
      });
      await user.click(deleteButton);

      // Check loading state while deletion is still in-flight
      expect(await screen.findByRole('button', { name: 'Deleting...' })).toBeDisabled();

      // Now let the deletions complete
      resolveDelete();

      // Wait for completion
      await waitFor(() => {
        expect(mockOnConfirmSuccess).toHaveBeenCalled();
      });
    });
  });

  describe('Edge Cases', () => {
    it('handles datasets with missing namespace gracefully', async () => {
      const user = userEvent.setup();
      const deleteRequests: Array<{ workspace: string; name: string }> = [];

      // Track delete requests
      server.use(
        http.delete(
          `${PLATFORM_BASE_URL}/apis/files/v2/workspaces/:workspace/filesets/:name`,
          ({ params }) => {
            deleteRequests.push({
              workspace: params.workspace as string,
              name: params.name as string,
            });
            return new HttpResponse(null, { status: 200 });
          }
        )
      );

      render(
        <DatasetBulkDeleteModal
          selectedDatasets={[datasetWithUndefinedNamespace]}
          onConfirmSuccess={mockOnConfirmSuccess}
        />
      );

      // Open modal
      const triggerButton = screen.getByTestId('bulk-delete-modal-trigger-button');
      await user.click(triggerButton);

      expect(await screen.findByRole('dialog')).toBeInTheDocument();

      // Click delete
      const deleteButton = within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Delete',
      });
      await user.click(deleteButton);

      // Wait for delete request
      await waitFor(() => {
        expect(deleteRequests).toHaveLength(0);
      });
    });

    it('handles datasets with missing name gracefully', async () => {
      const user = userEvent.setup();
      const deleteRequests: Array<{ workspace: string; name: string }> = [];

      // Track delete requests
      server.use(
        http.delete(
          `${PLATFORM_BASE_URL}/apis/files/v2/workspaces/:workspace/filesets/:name`,
          ({ params }) => {
            deleteRequests.push({
              workspace: params.workspace as string,
              name: params.name as string,
            });
            return new HttpResponse(null, { status: 200 });
          }
        )
      );

      render(
        <DatasetBulkDeleteModal
          selectedDatasets={[datasetWithUndefinedName]}
          onConfirmSuccess={mockOnConfirmSuccess}
        />
      );

      // Open modal
      const triggerButton = screen.getByTestId('bulk-delete-modal-trigger-button');
      await user.click(triggerButton);

      expect(await screen.findByRole('dialog')).toBeInTheDocument();

      // Click delete
      const deleteButton = within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Delete',
      });
      await user.click(deleteButton);

      // Wait for delete request
      await waitFor(() => {
        expect(deleteRequests).toHaveLength(0);
      });
    });

    it('works correctly with single dataset', async () => {
      const user = userEvent.setup();
      const deleteRequests: Array<{ workspace: string; name: string }> = [];

      // Track delete requests
      server.use(
        http.delete(
          `${PLATFORM_BASE_URL}/apis/files/v2/workspaces/:workspace/filesets/:name`,
          ({ params }) => {
            deleteRequests.push({
              workspace: params.workspace as string,
              name: params.name as string,
            });
            return new HttpResponse(null, { status: 200 });
          }
        )
      );

      render(
        <DatasetBulkDeleteModal
          selectedDatasets={[bulkDeleteTestDatasets[0]]}
          onConfirmSuccess={mockOnConfirmSuccess}
        />
      );

      // Open modal
      const triggerButton = screen.getByTestId('bulk-delete-modal-trigger-button');
      await user.click(triggerButton);

      expect(await screen.findByRole('dialog')).toBeInTheDocument();

      // Click delete
      const deleteButton = within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Delete',
      });
      await user.click(deleteButton);

      // Should call delete once
      await waitFor(() => {
        expect(deleteRequests).toHaveLength(1);
      });
      await waitFor(() => {
        expect(mockOnConfirmSuccess).toHaveBeenCalledTimes(1);
      });
    });
  });
});
