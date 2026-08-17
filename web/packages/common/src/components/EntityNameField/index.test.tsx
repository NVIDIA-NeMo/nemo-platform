// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { EntityNameField } from '@nemo/common/src/components/EntityNameField';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';

function Wrapper({
  checkAvailability,
}: {
  checkAvailability?: (name: string) => Promise<boolean>;
}) {
  const [value, setValue] = useState('');
  return (
    <EntityNameField
      entity="fileset"
      value={value}
      onChange={setValue}
      checkAvailability={checkAvailability}
    />
  );
}

describe('EntityNameField', () => {
  it('shows a live "will be created as" preview that sanitizes spaces and case without rewriting the input', async () => {
    const user = userEvent.setup();
    render(<Wrapper />);

    const input = screen.getByRole('textbox');
    await user.type(input, 'Foo bar');

    expect(input).toHaveValue('Foo bar');
    expect(screen.getByText('Your fileset will be created as foo-bar')).toBeInTheDocument();

    await user.clear(input);
    await user.type(input, 'MyProject');
    expect(input).toHaveValue('MyProject');
    expect(screen.getByText('Your fileset will be created as myproject')).toBeInTheDocument();
  });

  it('does not show a local validation error before blur, but does after', async () => {
    const user = userEvent.setup();
    render(<Wrapper />);

    const input = screen.getByRole('textbox');
    await user.type(input, '1a'); // invalid: must start with a lowercase letter

    expect(screen.queryByText(/must start with a lowercase letter/i)).not.toBeInTheDocument();

    await user.tab(); // blur

    expect(await screen.findByText(/must start with a lowercase letter/i)).toBeInTheDocument();
  });

  it('checks availability on keystroke and shows "Checking name..." while in flight', async () => {
    const user = userEvent.setup();
    const checkAvailability = vi.fn(() => new Promise<boolean>(() => {})); // never resolves
    render(<Wrapper checkAvailability={checkAvailability} />);

    await user.type(screen.getByRole('textbox'), 'taken-name');

    await waitFor(() => expect(checkAvailability).toHaveBeenCalledWith('taken-name'));
    expect(await screen.findByText('Checking name...')).toBeInTheDocument();
  });

  it('surfaces the conflict error immediately once the uniqueness check resolves, without needing blur', async () => {
    const user = userEvent.setup();
    const checkAvailability = vi.fn().mockResolvedValue(true);
    render(<Wrapper checkAvailability={checkAvailability} />);

    await user.type(screen.getByRole('textbox'), 'taken-name');

    expect(
      await screen.findByText('An fileset named taken-name already exists')
    ).toBeInTheDocument();
    // Input never had focus removed, confirming this bypasses the blur gate.
    expect(screen.getByRole('textbox')).toHaveFocus();
  });
});
