// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DeleteConfirmationModal } from '@studio/components/DeleteConfirmationModal';
import { dataset } from '@studio/mocks/datasets';
import { render, screen } from '@studio/tests/util/render';
import { waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('DeleteConfirmationModal', () => {
  const confirmationMessageText = `Type "${dataset.name}" to confirm`;

  it('renders confirmation input with correct placeholder text', async () => {
    render(
      <DeleteConfirmationModal
        onClose={vi.fn()}
        open
        onDelete={vi.fn().mockResolvedValue(true)}
        title="Test"
        confirmationText={dataset.name!}
        simpleConfirm={false}
      />
    );

    const confirmationInput = screen.getByRole('textbox', { name: /Confirmation/ });

    await waitFor(() =>
      expect(confirmationInput.getAttribute('placeholder')).toEqual(confirmationMessageText)
    );
  });

  it('renders validation error when confirmation input does not match name', async () => {
    const user = userEvent.setup();

    render(
      <DeleteConfirmationModal
        onClose={vi.fn()}
        open
        onDelete={vi.fn().mockResolvedValue(true)}
        title="Test"
        confirmationText={dataset.name!}
        simpleConfirm={false}
      />
    );

    const confirmationInput = screen.getByRole('textbox', { name: /Confirmation/ });
    const deleteButton = screen.getByRole('button', { name: /Delete/ });

    await user.type(confirmationInput, 'Some invalid input');
    await user.click(deleteButton);

    const confirmationMessage = await screen.findByText(confirmationMessageText);

    await waitFor(() => expect(confirmationMessage).toBeInTheDocument());
  });

  it('calls the delete function when confirmation passes', async () => {
    const spy = vi.fn();
    const user = userEvent.setup();

    render(
      <DeleteConfirmationModal
        open
        onClose={vi.fn()}
        onDelete={spy}
        title="Test"
        confirmationText={dataset.name!}
        simpleConfirm={false}
      />
    );

    const confirmationInput = screen.getByRole('textbox', { name: /Confirmation/ });
    const deleteButton = screen.getByRole('button', { name: /Delete/ });

    await user.type(confirmationInput, dataset.name || '');
    await user.click(deleteButton);

    await waitFor(() => expect(spy).toBeCalledTimes(1));
  });
});
