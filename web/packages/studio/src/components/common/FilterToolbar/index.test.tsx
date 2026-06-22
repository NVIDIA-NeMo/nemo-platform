// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DropdownEntry } from '@nvidia/foundations-react-core';
import { FilterToolbar } from '@studio/components/common/FilterToolbar/index';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('FilterToolbar', () => {
  const user = userEvent.setup();
  const mockItems: DropdownEntry[] = [
    {
      kind: 'radio',
      defaultValue: '',
      slotHeading: 'Test Filter',
      name: 'Test Filter',
      value: 'active-value',
      onValueChange: () => vi.fn(),
      items: [
        { children: 'Yes', value: 'yes' },
        { children: 'No', value: 'no' },
      ],
    },
  ];

  const query = { q: 'test' };
  const setQuery = vi.fn();

  const defaultProps = {
    items: mockItems,
    onRemoveAllFilters: vi.fn(),
    query,
    setQuery,
  };

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders basic elements correctly', () => {
    render(<FilterToolbar {...defaultProps} />);
    expect(screen.getByText('Filter')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Filter' })).toBeInTheDocument();
  });

  it('renders search bar with default props', async () => {
    render(<FilterToolbar {...defaultProps} />);
    const searchInput = screen.getByRole('textbox');
    expect(searchInput).toBeInTheDocument();
    await waitFor(() => expect(searchInput).toHaveValue('test'));
  });

  it('displays filter tags when filters are active', () => {
    render(<FilterToolbar {...defaultProps} />);
    // Assuming FilterTags renders something like "Test Filter: active-value"
    expect(screen.getAllByText(/Test Filter/).length).toBeGreaterThan(0);
  });

  it('handles disabled state correctly', () => {
    render(<FilterToolbar {...defaultProps} disabled />);
    const filterButton = screen.getByRole('button', { name: 'Filter' });
    const searchInput = screen.getByRole('textbox');
    expect(filterButton).toBeDisabled();
    expect(searchInput).toBeDisabled();
  });

  it('displays count label when provided', () => {
    const countLabel = '10 items';
    render(<FilterToolbar {...defaultProps} countLabel={countLabel} />);
    expect(screen.getByText(countLabel)).toBeInTheDocument();
  });

  it('handles search submission correctly', async () => {
    const onSubmit = vi.fn();
    render(<FilterToolbar {...defaultProps} searchBarProps={{ onSubmit }} />);
    const searchInput = screen.getByRole('textbox');
    await user.click(searchInput);
    await user.keyboard('{Enter}');
    expect(onSubmit).toHaveBeenCalledWith('test');
  });

  it('calls onRemoveAllFilters when clearing filters', async () => {
    render(<FilterToolbar {...defaultProps} />);
    const clearButton = screen.getByRole('button', { name: /clear all/i });
    await user.click(clearButton);
    expect(defaultProps.onRemoveAllFilters).toHaveBeenCalled();
  });
});
