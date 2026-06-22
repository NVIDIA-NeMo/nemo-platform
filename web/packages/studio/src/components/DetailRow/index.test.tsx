// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DetailRow } from '@studio/components/DetailRow';
import { render, screen, fireEvent } from '@testing-library/react';

describe('ToolRow', () => {
  const mockOnDelete = vi.fn();
  const mockOnView = vi.fn();
  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('rendering', () => {
    it('renders tool name', () => {
      render(<DetailRow label="test_function" />);

      expect(screen.getByText('test_function')).toBeInTheDocument();
    });

    it('does not render action buttons when isEditable is false', () => {
      render(<DetailRow label="test_function" isEditable={false} />);

      expect(screen.queryByLabelText('View metadata')).not.toBeInTheDocument();
      expect(screen.queryByLabelText('Remove tool')).not.toBeInTheDocument();
    });

    it('renders action buttons when isEditable is true', () => {
      render(
        <DetailRow label="test_function" isEditable onView={mockOnView} onDelete={mockOnDelete} />
      );

      expect(screen.getByLabelText('View metadata')).toBeInTheDocument();
      expect(screen.getByLabelText('Remove tool')).toBeInTheDocument();
    });

    it('applies disabled styling when disabled prop is true', () => {
      render(<DetailRow label="test_function" disabled />);

      expect(screen.getByTestId('detail-row-container').getAttribute('class')).toContain(
        'opacity-50'
      );
    });

    it('applies normal styling when disabled prop is false', () => {
      render(<DetailRow label="test_function" disabled={false} />);

      expect(screen.getByTestId('detail-row-container').getAttribute('class')).toContain(
        'opacity-100'
      );
    });
  });

  describe('interactions', () => {
    it('calls onViewMetadata when view button is clicked', () => {
      render(<DetailRow label="test_function" isEditable onView={mockOnView} />);

      fireEvent.click(screen.getByLabelText('View metadata'));

      expect(mockOnView).toHaveBeenCalledWith('test_function');
    });

    it('calls onDelete when delete button is clicked', () => {
      render(<DetailRow label="test_function" isEditable onDelete={mockOnDelete} />);

      fireEvent.click(screen.getByLabelText('Remove tool'));

      expect(mockOnDelete).toHaveBeenCalledWith('test_function');
    });

    it('does not call onViewMetadata when view button is disabled', () => {
      render(<DetailRow label="test_function" isEditable onView={mockOnView} disabled />);

      const viewButton = screen.getByLabelText('View metadata');
      expect(viewButton).toBeDisabled();

      fireEvent.click(viewButton);

      expect(mockOnView).not.toHaveBeenCalled();
    });

    it('does not call onDelete when delete button is disabled', () => {
      render(<DetailRow label="test_function" isEditable onDelete={mockOnDelete} disabled />);

      const deleteButton = screen.getByLabelText('Remove tool');
      expect(deleteButton).toBeDisabled();

      fireEvent.click(deleteButton);

      expect(mockOnDelete).not.toHaveBeenCalled();
    });
  });

  describe('conditional rendering', () => {
    it('does not render view button when onView is not provided', () => {
      render(<DetailRow label="test_function" isEditable onDelete={mockOnDelete} />);

      expect(screen.queryByLabelText('View metadata')).not.toBeInTheDocument();
      expect(screen.getByLabelText('Remove tool')).toBeInTheDocument();
    });

    it('does not render delete button when onDelete is not provided', () => {
      render(<DetailRow label="test_function" isEditable onView={mockOnView} />);

      expect(screen.getByLabelText('View metadata')).toBeInTheDocument();
      expect(screen.queryByLabelText('Remove tool')).not.toBeInTheDocument();
    });

    it('renders both buttons when both callbacks are provided', () => {
      render(
        <DetailRow label="test_function" isEditable onView={mockOnView} onDelete={mockOnDelete} />
      );

      expect(screen.getByLabelText('View metadata')).toBeInTheDocument();
      expect(screen.getByLabelText('Remove tool')).toBeInTheDocument();
    });
  });

  describe('accessibility', () => {
    it('has proper ARIA labels for buttons', () => {
      render(
        <DetailRow label="test_function" isEditable onView={mockOnView} onDelete={mockOnDelete} />
      );

      expect(screen.getByLabelText('View metadata')).toBeInTheDocument();
      expect(screen.getByLabelText('Remove tool')).toBeInTheDocument();
    });
  });
});
