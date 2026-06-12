// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ScrollTable,
  type PaginatedTableProps,
} from '@nemo/common/src/components/ScrollTable/index';
import type { TableColumnDefinition, TableRowDefinition } from '@nvidia/foundations-react-core';
import { render, screen } from '@testing-library/react';

describe('ScrollTable', () => {
  const mockColumns: TableColumnDefinition[] = [
    { children: 'Name' },
    { children: 'Age' },
    { children: 'Email' },
  ];

  const mockRows: TableRowDefinition[] = [
    {
      id: '1',
      cells: [{ children: 'John Doe' }, { children: '30' }, { children: 'john@example.com' }],
    },
    {
      id: '2',
      cells: [{ children: 'Jane Smith' }, { children: '25' }, { children: 'jane@example.com' }],
    },
  ];

  const defaultProps: PaginatedTableProps = {
    columns: mockColumns,
    rows: mockRows,
    paginationProps: {
      totalItems: mockRows.length,
      pageSize: 10,
    },
  };

  it('renders table with provided columns and rows', () => {
    render(<ScrollTable {...defaultProps} />);

    // Check that table content is rendered
    expect(screen.getByText('John Doe')).toBeInTheDocument();
    expect(screen.getByText('Jane Smith')).toBeInTheDocument();
    expect(screen.getByText('john@example.com')).toBeInTheDocument();
    expect(screen.getByText('jane@example.com')).toBeInTheDocument();
  });

  it('applies custom className when provided', () => {
    const customClass = 'custom-table-class';
    render(<ScrollTable {...defaultProps} className={customClass} />);

    // eslint-disable-next-line testing-library/no-node-access
    const container = screen.getByRole('table').closest(`.${customClass}`);
    expect(container).toBeInTheDocument();
  });

  describe('Loading state', () => {
    it('renders skeleton rows when loading is true', () => {
      render(<ScrollTable {...defaultProps} loading />);

      // Should show skeleton loading indicators instead of actual data
      expect(screen.queryByText('John Doe')).not.toBeInTheDocument();
      expect(screen.queryByText('Jane Smith')).not.toBeInTheDocument();

      // Check that skeleton elements are present (they should be animated)
      const skeletons = screen.queryAllByTestId('nv-skeleton');
      expect(skeletons).toHaveLength(
        defaultProps.paginationProps!.pageSize! * defaultProps.columns.length
      );
    });

    it('uses default pageSize of 10 when no pageSize provided in loading state', () => {
      const propsWithoutPageSize = {
        ...defaultProps,
        paginationProps: {
          totalItems: mockRows.length,
          // pageSize is intentionally omitted to test fallback
        },
      };
      render(<ScrollTable {...propsWithoutPageSize} loading />);

      const tableRows = screen.getAllByTestId('nv-table-row');
      expect(tableRows).toHaveLength(11); // 10 (default pageSize) + 1 for header row
    });
  });

  describe('Pagination', () => {
    it('does not render pagination when pagination prop is false', () => {
      render(<ScrollTable {...defaultProps} pagination={false} />);

      // Pagination component should not be in the DOM
      expect(screen.queryByTestId('nv-pagination-root')).not.toBeInTheDocument();
    });

    it('does not render pagination when pagination prop is undefined', () => {
      render(<ScrollTable {...defaultProps} />);

      expect(screen.queryByTestId('nv-pagination-root')).not.toBeInTheDocument();
    });

    it('renders pagination when pagination prop is true', async () => {
      const paginationProps = { pageSize: 10, totalItems: 100, page: 1 };
      render(<ScrollTable {...defaultProps} pagination paginationProps={paginationProps} />);

      // Should find pagination controls
      expect(await screen.findByTestId('nv-pagination-root')).toBeInTheDocument();
    });

    it('handles pagination with zero totalItems', async () => {
      render(<ScrollTable {...defaultProps} pagination />);

      // Should still render pagination component even with 0 total items
      expect(await screen.findByTestId('nv-pagination-root')).toBeInTheDocument();
    });
  });

  describe('Empty state', () => {
    it('renders default TableEmptyState when rows are empty and no custom slotEmptyState provided', () => {
      render(<ScrollTable columns={mockColumns} rows={[]} />);

      // Default empty state should be rendered
      expect(screen.getByText('No Entries Found')).toBeInTheDocument();
      expect(screen.getByText('No entries available.')).toBeInTheDocument();
    });

    it('renders custom slotEmptyState when provided and rows are empty', () => {
      render(
        <ScrollTable
          columns={mockColumns}
          rows={[]}
          slotEmptyState={<div data-testid="custom-empty-state">Custom Empty Message</div>}
        />
      );

      // Custom empty state should be rendered
      expect(screen.getByTestId('custom-empty-state')).toBeInTheDocument();
      expect(screen.getByText('Custom Empty Message')).toBeInTheDocument();

      // Default empty state should NOT be rendered
      expect(screen.queryByText('No Entries Found')).not.toBeInTheDocument();
    });

    it('does not render empty state when rows are present', () => {
      render(<ScrollTable {...defaultProps} />);

      // Empty state should not be rendered
      expect(screen.queryByText('No Entries Found')).not.toBeInTheDocument();

      // Actual data should be rendered
      expect(screen.getByText('John Doe')).toBeInTheDocument();
    });

    it('does not render empty state during loading even with empty rows', () => {
      render(<ScrollTable columns={mockColumns} rows={[]} loading />);

      // Empty state should not be rendered during loading
      expect(screen.queryByText('No Entries Found')).not.toBeInTheDocument();

      // Skeleton loading should be visible instead
      const skeletons = screen.queryAllByTestId('nv-skeleton');
      expect(skeletons.length).toBeGreaterThan(0);
    });
  });

  describe('Edge cases', () => {
    it('handles empty rows array', () => {
      render(<ScrollTable columns={mockColumns} rows={[]} />);

      // Table should still render with headers but no body rows
      expect(screen.getByRole('table')).toBeInTheDocument();
      const tableRows = screen.getAllByTestId('nv-table-row');
      expect(tableRows).toHaveLength(2); // Header row + empty state row
    });

    it('handles empty columns array', () => {
      render(<ScrollTable columns={[]} rows={mockRows} />);

      const tableRows = screen.getAllByTestId('nv-table-row');
      expect(tableRows).toHaveLength(mockRows.length + 1); // +1 for header row even though no columns
    });

    it('prioritizes loading state over actual data', () => {
      render(<ScrollTable {...defaultProps} loading />);

      // Should show loading state, not actual data
      expect(screen.queryByText('John Doe')).not.toBeInTheDocument();
      expect(screen.queryByText('Jane Smith')).not.toBeInTheDocument();
    });
  });

  describe('Memoization behavior', () => {
    it('updates content when loading state changes', () => {
      const { rerender } = render(<ScrollTable {...defaultProps} loading={false} />);

      // Should show actual data initially
      expect(screen.getByText('John Doe')).toBeInTheDocument();

      // Change to loading state
      rerender(<ScrollTable {...defaultProps} loading />);
      expect(screen.queryByText('John Doe')).not.toBeInTheDocument();

      // Change back to normal state
      rerender(<ScrollTable {...defaultProps} loading={false} />);
      expect(screen.getByText('John Doe')).toBeInTheDocument();
    });

    it('updates content when rows change', () => {
      const { rerender } = render(<ScrollTable {...defaultProps} />);

      expect(screen.getByText('John Doe')).toBeInTheDocument();

      const newRows = [
        {
          id: '3',
          cells: [{ children: 'New Person' }, { children: '35' }, { children: 'new@example.com' }],
        },
      ];

      rerender(<ScrollTable columns={mockColumns} rows={newRows} />);
      expect(screen.queryByText('John Doe')).not.toBeInTheDocument();
      expect(screen.getByText('New Person')).toBeInTheDocument();
    });
  });
});
