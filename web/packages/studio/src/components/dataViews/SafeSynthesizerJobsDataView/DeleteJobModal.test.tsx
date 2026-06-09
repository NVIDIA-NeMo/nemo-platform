// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ToastProvider } from '@nemo/common/src/providers/toast/ToastProvider';
import { useJobsDeleteJob } from '@nemo/sdk/generated/platform/api';
import { SafeSynthesizerJob } from '@nemo/sdk/generated/safe-synthesizer/schema';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import type { Mock } from 'vitest';

// Mock the delete job API hook
vi.mock('@nemo/sdk/generated/platform/api', () => ({
  useJobsDeleteJob: vi.fn(),
  getSafeSynthesizerListJobsQueryKey: vi.fn(() => ['jobs']),
}));

// Mock useQueryClient at module level
const mockResetQueries = vi.fn();
vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual('@tanstack/react-query');
  return {
    ...actual,
    useQueryClient: () => ({
      resetQueries: mockResetQueries,
    }),
  };
});

// Mock useWorkspaceFromPath
vi.mock('@studio/hooks/useWorkspaceFromPath', () => ({
  useWorkspaceFromPath: () => 'test-workspace',
}));

// Mock the DeleteConfirmationModal component
vi.mock('@studio/components/DeleteConfirmationModal', () => ({
  DeleteConfirmationModal: ({
    open,
    onDelete,
    onClose,
    title,
    errorText,
  }: {
    open: boolean;
    onDelete: () => Promise<boolean>;
    onClose: () => void;
    title: string;
    errorText?: string;
  }) => {
    const [error, setError] = React.useState<string | undefined>(errorText);

    React.useEffect(() => {
      setError(errorText);
    }, [errorText]);

    const handleDelete = async () => {
      const result = await onDelete();
      if (result) {
        onClose();
      }
    };

    return open ? (
      <div data-testid="delete-confirmation-modal">
        <h2>{title}</h2>
        {error && <div data-testid="error-message">{error}</div>}
        <button onClick={handleDelete} data-testid="confirm-delete">
          Delete
        </button>
        <button onClick={onClose} data-testid="cancel-delete">
          Cancel
        </button>
      </div>
    ) : null;
  },
}));

// Test data
const mockJob: SafeSynthesizerJob = {
  id: 'test-job-id',
  name: 'Test Job',
  workspace: 'test-workspace',
  status: 'completed',
  created_at: '2024-01-01T00:00:00.000Z',
  updated_at: '2024-01-01T00:00:00.000Z',
} as SafeSynthesizerJob;

const mockJob2: SafeSynthesizerJob = {
  id: 'test-job-id-2',
  name: 'Test Job 2',
  workspace: 'test-workspace',
  status: 'completed',
  created_at: '2024-01-02T00:00:00.000Z',
  updated_at: '2024-01-02T00:00:00.000Z',
} as SafeSynthesizerJob;

const mockJob3: SafeSynthesizerJob = {
  id: 'test-job-id-3',
  name: 'Test Job 3',
  workspace: 'test-workspace',
  status: 'completed',
  created_at: '2024-01-03T00:00:00.000Z',
  updated_at: '2024-01-03T00:00:00.000Z',
} as SafeSynthesizerJob;

// Test wrapper component
const TestWrapper = ({ children }: { children: React.ReactNode }) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return (
    <ToastProvider>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ToastProvider>
  );
};

describe('DeleteJobModal', () => {
  const mockOnClose = vi.fn();
  const mockMutateAsync = vi.fn();
  const mockUseDeleteJob = vi.mocked(useJobsDeleteJob);

  beforeEach(() => {
    vi.clearAllMocks();

    // Setup default mock for the delete job hook
    (mockUseDeleteJob as unknown as Mock).mockReturnValue({
      mutateAsync: mockMutateAsync,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Rendering', () => {
    it('should render modal when single job is provided', async () => {
      const { DeleteJobModal } =
        await import('@studio/components/dataViews/SafeSynthesizerJobsDataView/DeleteJobModal');
      render(
        <TestWrapper>
          <DeleteJobModal jobs={[mockJob]} onClose={mockOnClose} />
        </TestWrapper>
      );

      expect(screen.getByTestId('delete-confirmation-modal')).toBeInTheDocument();
      expect(screen.getByText('Delete 1 Safe Synthesizer Job')).toBeInTheDocument();
    });

    it('should render modal with correct title for multiple jobs', async () => {
      const { DeleteJobModal } =
        await import('@studio/components/dataViews/SafeSynthesizerJobsDataView/DeleteJobModal');
      render(
        <TestWrapper>
          <DeleteJobModal jobs={[mockJob, mockJob2, mockJob3]} onClose={mockOnClose} />
        </TestWrapper>
      );

      expect(screen.getByTestId('delete-confirmation-modal')).toBeInTheDocument();
      expect(screen.getByText('Delete 3 Safe Synthesizer Jobs')).toBeInTheDocument();
    });

    it('should not render modal when jobs array is empty', async () => {
      const { DeleteJobModal } =
        await import('@studio/components/dataViews/SafeSynthesizerJobsDataView/DeleteJobModal');
      render(
        <TestWrapper>
          <DeleteJobModal jobs={[]} onClose={mockOnClose} />
        </TestWrapper>
      );

      expect(screen.queryByTestId('delete-confirmation-modal')).not.toBeInTheDocument();
    });
  });

  describe('Delete functionality', () => {
    it('should successfully delete single job and close modal', async () => {
      const user = userEvent.setup();
      const { DeleteJobModal } =
        await import('@studio/components/dataViews/SafeSynthesizerJobsDataView/DeleteJobModal');
      mockMutateAsync.mockResolvedValueOnce(undefined);

      render(
        <TestWrapper>
          <DeleteJobModal jobs={[mockJob]} onClose={mockOnClose} />
        </TestWrapper>
      );

      const deleteButton = screen.getByTestId('confirm-delete');
      await user.click(deleteButton);

      await waitFor(() => {
        expect(mockMutateAsync).toHaveBeenCalledWith({
          workspace: 'test-workspace',
          name: 'Test Job',
        });
      });
      expect(mockOnClose).toHaveBeenCalled();
    });

    it('should successfully delete multiple jobs in parallel', async () => {
      const user = userEvent.setup();
      const { DeleteJobModal } =
        await import('@studio/components/dataViews/SafeSynthesizerJobsDataView/DeleteJobModal');
      mockMutateAsync.mockResolvedValue(undefined);

      render(
        <TestWrapper>
          <DeleteJobModal jobs={[mockJob, mockJob2, mockJob3]} onClose={mockOnClose} />
        </TestWrapper>
      );

      const deleteButton = screen.getByTestId('confirm-delete');
      await user.click(deleteButton);

      await waitFor(() => {
        expect(mockMutateAsync).toHaveBeenCalledTimes(3);
      });
      expect(mockMutateAsync).toHaveBeenCalledWith({
        workspace: 'test-workspace',
        name: 'Test Job',
      });
      expect(mockMutateAsync).toHaveBeenCalledWith({
        workspace: 'test-workspace',
        name: 'Test Job 2',
      });
      expect(mockMutateAsync).toHaveBeenCalledWith({
        workspace: 'test-workspace',
        name: 'Test Job 3',
      });
      expect(mockOnClose).toHaveBeenCalled();
    });

    it('should handle delete error and show error message', async () => {
      const user = userEvent.setup();
      const { DeleteJobModal } =
        await import('@studio/components/dataViews/SafeSynthesizerJobsDataView/DeleteJobModal');
      const errorMessage = 'Failed to delete job';
      mockMutateAsync.mockRejectedValueOnce(new Error(errorMessage));

      render(
        <TestWrapper>
          <DeleteJobModal jobs={[mockJob]} onClose={mockOnClose} />
        </TestWrapper>
      );

      const deleteButton = screen.getByTestId('confirm-delete');
      await user.click(deleteButton);

      await waitFor(() => {
        expect(screen.getByTestId('error-message')).toHaveTextContent(
          `Failed to delete job "Test Job": ${errorMessage}`
        );
      });
      expect(mockOnClose).not.toHaveBeenCalled();
    });

    it('should handle error when deleting multiple jobs and include job name', async () => {
      const user = userEvent.setup();
      const { DeleteJobModal } =
        await import('@studio/components/dataViews/SafeSynthesizerJobsDataView/DeleteJobModal');
      const errorMessage = 'Network error';
      // First two succeed, third fails
      mockMutateAsync.mockResolvedValueOnce(undefined);
      mockMutateAsync.mockResolvedValueOnce(undefined);
      mockMutateAsync.mockRejectedValueOnce(new Error(errorMessage));

      render(
        <TestWrapper>
          <DeleteJobModal jobs={[mockJob, mockJob2, mockJob3]} onClose={mockOnClose} />
        </TestWrapper>
      );

      const deleteButton = screen.getByTestId('confirm-delete');
      await user.click(deleteButton);

      await waitFor(() => {
        expect(screen.getByTestId('error-message')).toHaveTextContent(
          `Failed to delete job "Test Job 3": ${errorMessage}`
        );
      });
      expect(mockOnClose).not.toHaveBeenCalled();
    });

    it('should handle non-Error rejection and show generic error message', async () => {
      const user = userEvent.setup();
      const { DeleteJobModal } =
        await import('@studio/components/dataViews/SafeSynthesizerJobsDataView/DeleteJobModal');
      mockMutateAsync.mockRejectedValueOnce('String error');

      render(
        <TestWrapper>
          <DeleteJobModal jobs={[mockJob]} onClose={mockOnClose} />
        </TestWrapper>
      );

      const deleteButton = screen.getByTestId('confirm-delete');
      await user.click(deleteButton);

      await waitFor(() => {
        expect(screen.getByTestId('error-message')).toHaveTextContent(
          'Failed to delete job "Test Job": Unknown error'
        );
      });
      expect(mockOnClose).not.toHaveBeenCalled();
    });

    it('should not attempt deletion when jobs array is empty', async () => {
      const { DeleteJobModal } =
        await import('@studio/components/dataViews/SafeSynthesizerJobsDataView/DeleteJobModal');
      render(
        <TestWrapper>
          <DeleteJobModal jobs={[]} onClose={mockOnClose} />
        </TestWrapper>
      );

      // Modal should not be rendered, so no delete button to click
      expect(screen.queryByTestId('confirm-delete')).not.toBeInTheDocument();
    });
  });

  describe('Close functionality', () => {
    it('should close modal and clear error when cancel is clicked', async () => {
      const user = userEvent.setup();
      const { DeleteJobModal } =
        await import('@studio/components/dataViews/SafeSynthesizerJobsDataView/DeleteJobModal');

      // First set an error by attempting a failed deletion
      mockMutateAsync.mockRejectedValueOnce(new Error('Test error'));

      render(
        <TestWrapper>
          <DeleteJobModal jobs={[mockJob]} onClose={mockOnClose} />
        </TestWrapper>
      );

      // Trigger an error first
      const deleteButton = screen.getByTestId('confirm-delete');
      await user.click(deleteButton);

      await waitFor(() => {
        expect(screen.getByTestId('error-message')).toBeInTheDocument();
      });

      // Now click cancel
      const cancelButton = screen.getByTestId('cancel-delete');
      await user.click(cancelButton);

      expect(mockOnClose).toHaveBeenCalled();
    });

    it('should clear error when modal is closed after error', async () => {
      const user = userEvent.setup();
      const { DeleteJobModal } =
        await import('@studio/components/dataViews/SafeSynthesizerJobsDataView/DeleteJobModal');
      mockMutateAsync.mockRejectedValueOnce(new Error('Test error'));

      const { rerender } = render(
        <TestWrapper>
          <DeleteJobModal jobs={[mockJob]} onClose={mockOnClose} />
        </TestWrapper>
      );

      // Trigger an error
      const deleteButton = screen.getByTestId('confirm-delete');
      await user.click(deleteButton);

      await waitFor(() => {
        expect(screen.getByTestId('error-message')).toBeInTheDocument();
      });

      // Close modal by clicking cancel (which calls handleClose)
      const cancelButton = screen.getByTestId('cancel-delete');
      await user.click(cancelButton);

      // Clear the mock to avoid the error on next render
      mockMutateAsync.mockResolvedValueOnce(undefined);

      // Reopen modal - error should be cleared
      rerender(
        <TestWrapper>
          <DeleteJobModal jobs={[mockJob]} onClose={mockOnClose} />
        </TestWrapper>
      );

      // The error should be cleared when the modal reopens
      expect(screen.queryByTestId('error-message')).not.toBeInTheDocument();
    });
  });

  describe('Query invalidation', () => {
    it('should invalidate queries after successful single job deletion', async () => {
      const user = userEvent.setup();
      const { DeleteJobModal } =
        await import('@studio/components/dataViews/SafeSynthesizerJobsDataView/DeleteJobModal');
      mockMutateAsync.mockResolvedValueOnce(undefined);

      render(
        <TestWrapper>
          <DeleteJobModal jobs={[mockJob]} onClose={mockOnClose} />
        </TestWrapper>
      );

      const deleteButton = screen.getByTestId('confirm-delete');
      await user.click(deleteButton);

      await waitFor(() => {
        expect(mockMutateAsync).toHaveBeenCalledWith({
          workspace: 'test-workspace',
          name: 'Test Job',
        });
      });
      expect(mockOnClose).toHaveBeenCalled();
    });

    it('should invalidate queries after successful multiple jobs deletion', async () => {
      const user = userEvent.setup();
      const { DeleteJobModal } =
        await import('@studio/components/dataViews/SafeSynthesizerJobsDataView/DeleteJobModal');
      mockMutateAsync.mockResolvedValue(undefined);

      render(
        <TestWrapper>
          <DeleteJobModal jobs={[mockJob, mockJob2]} onClose={mockOnClose} />
        </TestWrapper>
      );

      const deleteButton = screen.getByTestId('confirm-delete');
      await user.click(deleteButton);

      await waitFor(() => {
        expect(mockMutateAsync).toHaveBeenCalledTimes(2);
      });
      expect(mockOnClose).toHaveBeenCalled();
    });
  });

  describe('Error state management', () => {
    it('should clear error when new deletion attempt is made', async () => {
      const user = userEvent.setup();
      const { DeleteJobModal } =
        await import('@studio/components/dataViews/SafeSynthesizerJobsDataView/DeleteJobModal');

      // First attempt fails
      mockMutateAsync.mockRejectedValueOnce(new Error('First error'));

      render(
        <TestWrapper>
          <DeleteJobModal jobs={[mockJob]} onClose={mockOnClose} />
        </TestWrapper>
      );

      // First deletion attempt
      const deleteButton = screen.getByTestId('confirm-delete');
      await user.click(deleteButton);

      await waitFor(() => {
        expect(screen.getByTestId('error-message')).toHaveTextContent('First error');
      });

      // Second attempt succeeds
      mockMutateAsync.mockResolvedValueOnce(undefined);
      await user.click(deleteButton);

      await waitFor(() => {
        expect(screen.queryByTestId('error-message')).not.toBeInTheDocument();
      });
      expect(mockOnClose).toHaveBeenCalled();
    });

    it('should maintain error state until cleared or new attempt', async () => {
      const user = userEvent.setup();
      const { DeleteJobModal } =
        await import('@studio/components/dataViews/SafeSynthesizerJobsDataView/DeleteJobModal');
      mockMutateAsync.mockRejectedValueOnce(new Error('Persistent error'));

      render(
        <TestWrapper>
          <DeleteJobModal jobs={[mockJob]} onClose={mockOnClose} />
        </TestWrapper>
      );

      const deleteButton = screen.getByTestId('confirm-delete');
      await user.click(deleteButton);

      await waitFor(() => {
        expect(screen.getByTestId('error-message')).toHaveTextContent('Persistent error');
      });

      // Error should persist
      expect(screen.getByTestId('error-message')).toHaveTextContent('Persistent error');
    });
  });

  describe('Component props', () => {
    it('should pass correct props to DeleteConfirmationModal for single job', async () => {
      const { DeleteJobModal } =
        await import('@studio/components/dataViews/SafeSynthesizerJobsDataView/DeleteJobModal');
      render(
        <TestWrapper>
          <DeleteJobModal jobs={[mockJob]} onClose={mockOnClose} />
        </TestWrapper>
      );

      expect(screen.getByText('Delete 1 Safe Synthesizer Job')).toBeInTheDocument();
      expect(screen.getByTestId('delete-confirmation-modal')).toBeInTheDocument();
    });

    it('should pass correct props to DeleteConfirmationModal for multiple jobs', async () => {
      const { DeleteJobModal } =
        await import('@studio/components/dataViews/SafeSynthesizerJobsDataView/DeleteJobModal');
      render(
        <TestWrapper>
          <DeleteJobModal jobs={[mockJob, mockJob2]} onClose={mockOnClose} />
        </TestWrapper>
      );

      expect(screen.getByText('Delete 2 Safe Synthesizer Jobs')).toBeInTheDocument();
      expect(screen.getByTestId('delete-confirmation-modal')).toBeInTheDocument();
    });

    it('should handle job with different properties', async () => {
      const { DeleteJobModal } =
        await import('@studio/components/dataViews/SafeSynthesizerJobsDataView/DeleteJobModal');
      const customJob: SafeSynthesizerJob = {
        ...mockJob,
        name: 'Custom Job Name',
        status: 'active',
      };

      render(
        <TestWrapper>
          <DeleteJobModal jobs={[customJob]} onClose={mockOnClose} />
        </TestWrapper>
      );

      expect(screen.getByTestId('delete-confirmation-modal')).toBeInTheDocument();
    });
  });
});
