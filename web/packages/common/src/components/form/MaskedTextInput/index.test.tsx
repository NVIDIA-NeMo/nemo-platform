// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { MaskedTextInput } from '@nemo/common/src/components/form/MaskedTextInput/index';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('MaskedTextInput', () => {
  const user = userEvent.setup();

  it('renders as a password input by default', () => {
    render(<MaskedTextInput defaultValue="secret" />);
    expect(screen.getByDisplayValue('secret')).toHaveAttribute('type', 'password');
  });

  it('toggles visibility on button click (uncontrolled)', async () => {
    render(<MaskedTextInput defaultValue="secret" />);

    await user.click(screen.getByRole('button', { name: /show value/i }));
    expect(screen.getByDisplayValue('secret')).toHaveAttribute('type', 'text');
    expect(screen.getByRole('button', { name: /hide value/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /hide value/i }));
    expect(screen.getByDisplayValue('secret')).toHaveAttribute('type', 'password');
  });

  it('respects the controlled `visible` prop', async () => {
    const onVisibilityChange = vi.fn();
    const { rerender } = render(
      <MaskedTextInput
        defaultValue="secret"
        visible={false}
        onVisibilityChange={onVisibilityChange}
      />
    );
    expect(screen.getByDisplayValue('secret')).toHaveAttribute('type', 'password');

    await user.click(screen.getByRole('button', { name: /show value/i }));
    expect(onVisibilityChange).toHaveBeenCalledWith(true);
    // Still password because the parent hasn't flipped `visible`.
    expect(screen.getByDisplayValue('secret')).toHaveAttribute('type', 'password');

    rerender(
      <MaskedTextInput defaultValue="secret" visible onVisibilityChange={onVisibilityChange} />
    );
    expect(screen.getByDisplayValue('secret')).toHaveAttribute('type', 'text');
  });

  it('disables the toggle button when disabled', () => {
    render(<MaskedTextInput defaultValue="secret" disabled />);
    expect(screen.getByRole('button', { name: /show value/i })).toBeDisabled();
  });
});
