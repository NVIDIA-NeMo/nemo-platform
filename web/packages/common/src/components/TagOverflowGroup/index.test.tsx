// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { TagOverflowGroup } from '@nemo/common/src/components/TagOverflowGroup/index';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('TagOverflowGroup', () => {
  const defaultProps = {
    resetFilters: vi.fn(),
  };

  it('renders children', () => {
    render(
      <TagOverflowGroup {...defaultProps}>
        <span data-testid="tag-1">Tag 1</span>
        <span data-testid="tag-2">Tag 2</span>
      </TagOverflowGroup>
    );

    expect(screen.getByTestId('tag-1')).toBeInTheDocument();
    expect(screen.getByTestId('tag-2')).toBeInTheDocument();
  });

  it('renders default clear button text', () => {
    render(
      <TagOverflowGroup {...defaultProps}>
        <span>Tag 1</span>
      </TagOverflowGroup>
    );

    // Component renders Clear Filters button (may appear multiple times due to overflow logic)
    expect(screen.getAllByText('Clear Filters').length).toBeGreaterThan(0);
  });

  it('renders custom clear button text', () => {
    render(
      <TagOverflowGroup {...defaultProps} clearButtonText="Reset All">
        <span>Tag 1</span>
      </TagOverflowGroup>
    );

    expect(screen.getAllByText('Reset All').length).toBeGreaterThan(0);
    expect(screen.queryByText('Clear Filters')).not.toBeInTheDocument();
  });

  it('calls resetFilters when clear button is clicked', async () => {
    const user = userEvent.setup();
    const resetFiltersMock = vi.fn();

    render(
      <TagOverflowGroup resetFilters={resetFiltersMock}>
        <span>Tag 1</span>
      </TagOverflowGroup>
    );

    // Get the first Clear Filters button
    const clearButtons = screen.getAllByText('Clear Filters');
    await user.click(clearButtons[0]);

    expect(resetFiltersMock).toHaveBeenCalledTimes(1);
  });

  it('renders with no children', () => {
    render(<TagOverflowGroup {...defaultProps}>{null}</TagOverflowGroup>);

    // Should still render the clear button (may appear multiple times)
    expect(screen.getAllByText('Clear Filters').length).toBeGreaterThan(0);
  });
});
