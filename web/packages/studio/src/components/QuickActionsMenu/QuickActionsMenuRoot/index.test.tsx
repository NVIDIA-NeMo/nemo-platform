// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { QuickActionsMenuRoot } from '@studio/components/QuickActionsMenu/QuickActionsMenuRoot';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('QuickActionsMenu', () => {
  it('should render trigger without menu until clicked', async () => {
    const user = userEvent.setup();
    render(<QuickActionsMenuRoot actions={[]} />);

    const trigger = screen.getByTestId('quick-actions-menu-trigger');
    const content = screen.queryByTestId('quick-actions-menu-content');

    expect(trigger).toBeDefined();
    // KUI v1.0 popover content stays in the DOM but is closed (no popover-open attr)
    expect(content).not.toHaveAttribute('popover-open');

    await user.click(trigger);
    expect(screen.getByTestId('quick-actions-menu-content')).toHaveAttribute('popover-open');
  });
  it('should render correct number of menu items', async () => {
    const user = userEvent.setup();

    render(
      <QuickActionsMenuRoot
        actions={[
          { label: 'action1', onSelect: () => alert('action1') },
          { label: 'action2', onSelect: () => alert('action2') },
        ]}
      />
    );

    const trigger = screen.getByTestId('quick-actions-menu-trigger');
    await user.click(trigger);

    expect(screen.getAllByTestId('quick-actions-menu-item')).toHaveLength(2);
  });
});
