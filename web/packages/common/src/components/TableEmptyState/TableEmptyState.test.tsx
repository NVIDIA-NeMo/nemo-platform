// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState/index';
import { Button } from '@nvidia/foundations-react-core';
import { render, screen } from '@testing-library/react';

describe('TableEmptyState', () => {
  it('renders with required props', () => {
    const header = 'No Items Found';
    const message = 'There are no items to display';

    render(<TableEmptyState header={header} emptyMessage={message} />);

    expect(screen.getByText(header)).toBeInTheDocument();
    expect(screen.getByText(message)).toBeInTheDocument();
    // Default icon should be rendered
    expect(screen.getByTestId('icon-folder-open')).toBeInTheDocument();
  });

  it('renders with custom icon', () => {
    const customIcon = <div data-testid="custom-icon">🔍</div>;

    render(<TableEmptyState header="Test Header" emptyMessage="Test Message" icon={customIcon} />);

    expect(screen.getByTestId('custom-icon')).toBeInTheDocument();
    // Default icon should not be present
    expect(screen.queryByTestId('icon-folder-open')).not.toBeInTheDocument();
  });

  it('renders with action buttons', () => {
    const actions = (
      <>
        <Button data-testid="action-1">Action 1</Button>
        <Button data-testid="action-2">Action 2</Button>
      </>
    );

    render(<TableEmptyState header="Test Header" emptyMessage="Test Message" actions={actions} />);

    expect(screen.getByTestId('action-1')).toBeInTheDocument();
    expect(screen.getByTestId('action-2')).toBeInTheDocument();
  });
});
