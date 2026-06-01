// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { EvaluationMetricBulkDeleteModal } from '@studio/components/evaluation/Metrics/EvaluationMetricBulkDeleteModal';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { mockUseParams } from '@studio/tests/util/mockUseParams';
import { customRender as render } from '@studio/tests/util/render';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const TEST_WORKSPACE = 'test-workspace';

// Mock the delete API
const mockDeleteMetric = vi.fn();
vi.mock('@nemo/sdk/generated/platform/api', async (importOriginal) => {
  const original = await importOriginal();
  return {
    // @ts-expect-error expect issue here with spread
    ...original,
    useEvaluationDeleteMetric: vi.fn(() => ({
      mutateAsync: mockDeleteMetric,
    })),
  };
});

describe('EvaluationMetricBulkDeleteModal', () => {
  const mockMetrics = [{ name: 'metric-1' }, { name: 'metric-2' }];

  const mockOnConfirmSuccess = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockDeleteMetric.mockResolvedValue(undefined);
    mockUseParams({
      [ROUTE_PARAMS.workspace]: TEST_WORKSPACE,
    });
  });

  describe('Rendering', () => {
    it('should render trigger button with correct text', async () => {
      render(
        <EvaluationMetricBulkDeleteModal
          selectedMetrics={mockMetrics}
          onConfirmSuccess={mockOnConfirmSuccess}
        />
      );

      expect(await screen.findByTestId('bulk-delete-modal-trigger-button')).toBeInTheDocument();
      expect(screen.getByText('Delete')).toBeInTheDocument();
    });

    it('should show modal when trigger is clicked', async () => {
      const user = userEvent.setup();

      render(
        <EvaluationMetricBulkDeleteModal
          selectedMetrics={mockMetrics}
          onConfirmSuccess={mockOnConfirmSuccess}
        />
      );

      const triggerButton = await screen.findByTestId('bulk-delete-modal-trigger-button');
      await user.click(triggerButton);

      expect(await screen.findByText('Delete 2 Metrics')).toBeInTheDocument();
      expect(
        screen.getByText('Are you sure you want to delete 2 metrics? This action cannot be undone.')
      ).toBeInTheDocument();
    });

    it('should show singular form for single metric', async () => {
      const user = userEvent.setup();

      render(
        <EvaluationMetricBulkDeleteModal
          selectedMetrics={[mockMetrics[0]]}
          onConfirmSuccess={mockOnConfirmSuccess}
        />
      );

      const triggerButton = await screen.findByTestId('bulk-delete-modal-trigger-button');
      await user.click(triggerButton);

      expect(await screen.findByText('Delete 1 Metric')).toBeInTheDocument();
    });
  });

  describe('Modal Actions', () => {
    it('should close modal when cancel is clicked', async () => {
      const user = userEvent.setup();

      render(
        <EvaluationMetricBulkDeleteModal
          selectedMetrics={mockMetrics}
          onConfirmSuccess={mockOnConfirmSuccess}
        />
      );

      const triggerButton = await screen.findByTestId('bulk-delete-modal-trigger-button');
      await user.click(triggerButton);

      await waitFor(() => {
        expect(screen.getByText('Delete 2 Metrics')).toBeInTheDocument();
      });

      const cancelButton = screen.getByRole('button', { name: 'Cancel' });
      await user.click(cancelButton);

      await waitFor(() => {
        expect(screen.queryByText('Delete 2 Metrics')).not.toBeInTheDocument();
      });
    });

    it('should call onConfirmSuccess and close modal when delete is confirmed', async () => {
      const user = userEvent.setup();

      render(
        <EvaluationMetricBulkDeleteModal
          selectedMetrics={mockMetrics}
          onConfirmSuccess={mockOnConfirmSuccess}
        />
      );

      const triggerButton = await screen.findByTestId('bulk-delete-modal-trigger-button');
      await user.click(triggerButton);

      expect(await screen.findByText('Delete 2 Metrics')).toBeInTheDocument();

      const deleteButton = within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Delete',
      });
      await user.click(deleteButton);

      await waitFor(() => {
        expect(mockDeleteMetric).toHaveBeenCalledTimes(2);
      });
      await waitFor(() => {
        expect(mockDeleteMetric).toHaveBeenCalledWith({
          workspace: TEST_WORKSPACE,
          name: 'metric-1',
        });
      });
      await waitFor(() => {
        expect(mockDeleteMetric).toHaveBeenCalledWith({
          workspace: TEST_WORKSPACE,
          name: 'metric-2',
        });
      });
      await waitFor(() => {
        expect(mockOnConfirmSuccess).toHaveBeenCalled();
      });

      await waitFor(() => {
        expect(screen.queryByText('Delete 2 Metrics')).not.toBeInTheDocument();
      });
    });

    it('should handle deletion errors gracefully', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      mockDeleteMetric.mockRejectedValue(new Error('Delete failed'));
      const user = userEvent.setup();

      render(
        <EvaluationMetricBulkDeleteModal
          selectedMetrics={mockMetrics}
          onConfirmSuccess={mockOnConfirmSuccess}
        />
      );

      const triggerButton = await screen.findByTestId('bulk-delete-modal-trigger-button');
      await user.click(triggerButton);

      expect(await screen.findByText('Delete 2 Metrics')).toBeInTheDocument();

      const deleteButton = within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Delete',
      });
      await user.click(deleteButton);

      await waitFor(() => {
        expect(consoleSpy).toHaveBeenCalledWith(
          'Failed to delete evaluation metrics:',
          expect.any(Error)
        );
      });
      await waitFor(() => {
        expect(mockOnConfirmSuccess).not.toHaveBeenCalled();
      });

      consoleSpy.mockRestore();
    });

    it('should filter out metrics without valid names', async () => {
      const metricsWithInvalidNames = [
        { name: undefined as unknown as string },
        mockMetrics[1],
        { name: 'metric-3' },
      ];
      const user = userEvent.setup();

      render(
        <EvaluationMetricBulkDeleteModal
          selectedMetrics={metricsWithInvalidNames}
          onConfirmSuccess={mockOnConfirmSuccess}
        />
      );

      const triggerButton = await screen.findByTestId('bulk-delete-modal-trigger-button');
      await user.click(triggerButton);

      expect(await screen.findByText('Delete 2 Metrics')).toBeInTheDocument();

      const deleteButton = within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Delete',
      });
      await user.click(deleteButton);

      await waitFor(() => {
        expect(mockDeleteMetric).toHaveBeenCalledTimes(2);
      });
      await waitFor(() => {
        expect(mockDeleteMetric).toHaveBeenCalledWith({
          workspace: TEST_WORKSPACE,
          name: 'metric-2',
        });
      });
      await waitFor(() => {
        expect(mockDeleteMetric).toHaveBeenCalledWith({
          workspace: TEST_WORKSPACE,
          name: 'metric-3',
        });
      });
    });
  });

  describe('Modal State Management', () => {
    it('should handle empty selected metrics array', async () => {
      render(
        <EvaluationMetricBulkDeleteModal
          selectedMetrics={[]}
          onConfirmSuccess={mockOnConfirmSuccess}
        />
      );

      expect(await screen.findByTestId('bulk-delete-modal-trigger-button')).toBeInTheDocument();
      expect(screen.getByText('Delete')).toBeInTheDocument();
    });
  });
});
