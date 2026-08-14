// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CreateSecretModal } from '@nemo/common/src/components/CreateSecretModal';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// KUI's FormField root carries the same aria-label as the input, so scope to the input.
const field = (label: string): HTMLElement => screen.getByLabelText(label, { selector: 'input' });

const fillForm = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.type(field('Name'), 'my-secret');
  await user.type(field('Value'), 'hunter2');
};

describe('CreateSecretModal', () => {
  const user = userEvent.setup();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('submits the form values, notifies, and closes', async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();
    const onNotify = vi.fn();

    render(<CreateSecretModal open onClose={onClose} onCreate={onCreate} onNotify={onNotify} />);

    await fillForm(user);
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() =>
      expect(onCreate).toHaveBeenCalledWith({
        name: 'my-secret',
        description: '',
        value: 'hunter2',
      })
    );
    expect(onNotify).toHaveBeenCalledWith('Secret created successfully', 'success', undefined);
    expect(onClose).toHaveBeenCalled();
  });

  it('stays open when onCreate rejects', async () => {
    const onCreate = vi.fn().mockRejectedValue(new Error('boom'));
    const onClose = vi.fn();
    const onNotify = vi.fn();

    render(
      <CreateSecretModal
        open
        onClose={onClose}
        onCreate={onCreate}
        onNotify={onNotify}
        errorText="Secret already exists"
      />
    );

    await fillForm(user);
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(onCreate).toHaveBeenCalled());
    expect(onClose).not.toHaveBeenCalled();
    expect(onNotify).not.toHaveBeenCalled();
    expect(screen.getByText('Secret already exists')).toBeInTheDocument();
  });

  it('does not submit without a value', async () => {
    const onCreate = vi.fn();

    render(<CreateSecretModal open onClose={vi.fn()} onCreate={onCreate} onNotify={vi.fn()} />);

    await user.type(field('Name'), 'my-secret');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await screen.findByText('Secret value is required');
    expect(onCreate).not.toHaveBeenCalled();
  });
});
