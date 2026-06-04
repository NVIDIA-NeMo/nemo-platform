// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { PanelFooterAccordion } from '.';

describe('PanelFooterAccordion', () => {
  it('should render a panel footer accordion', async () => {
    const user = userEvent.setup();
    render(<PanelFooterAccordion slotTrigger="Test" slotContent="Value" value="Value" />);
    const trigger = screen.getByText('Test');
    expect(trigger).toBeInTheDocument();
    const content = screen.getByText('Value');
    expect(content).toHaveAttribute('data-state', 'closed');
    await user.click(trigger);
    expect(screen.getByText('Value')).toHaveAttribute('data-state', 'open');
  });
});
