// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { QuickActionsMenuDefault } from '@studio/components/QuickActionsMenu/QuickActionsMenuDefault';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter as Router } from 'react-router-dom';

describe('QuickActionsMenu', () => {
  it('should selectively render menu items in default menu', async () => {
    const user = userEvent.setup();
    render(
      <Router>
        <QuickActionsMenuDefault openTarget="test" editAction={() => alert('edit me')} />
      </Router>
    );

    const trigger = screen.getByTestId('quick-actions-menu-trigger');
    await user.click(trigger);

    expect(screen.getAllByTestId('quick-actions-menu-item')).toHaveLength(2);
  });
});
