// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Renders this story file's own exported render components directly — there
// is no separate `EntityNamingExample` component export to import. This
// proves the pattern described in entity-naming.md is actually
// implementable with plain react-hook-form + zod, not a claim about a
// shared component's API.
import {
  renderDefault as Default,
  renderNothingValidToSubmit as NothingValidToSubmit,
  renderWithUniquenessCheck as WithUniquenessCheck,
  // eslint-disable-next-line import/extensions -- `.stories` here is a filename segment, not a real file extension
} from '@nemo/common/src/components/EntityNamingExample/EntityNamingExample.stories';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const getByHelperText = (text: string) =>
  screen.getByText(
    (_content, element) => element?.textContent?.replace(/\s+/g, ' ').trim() === text
  );

describe('entity-naming pattern (react-hook-form + zod)', () => {
  it('shows a live "will be created as" preview that sanitizes spaces and case without rewriting the input', async () => {
    const user = userEvent.setup();
    render(<Default />);

    const input = screen.getByRole('textbox');
    await user.type(input, 'Foo bar');

    expect(input).toHaveValue('Foo bar');
    expect(getByHelperText('Your fileset will be created as foo-bar')).toBeInTheDocument();
    expect(screen.getByText('foo-bar')).toHaveClass('text-primary');
  });

  it('does not show a local error after blur for a name that just needs sanitizing, since submit receives the transformed name', async () => {
    const user = userEvent.setup();
    render(<Default />);

    const input = screen.getByRole('textbox');
    await user.type(input, '1a Bad Name!!');
    await user.tab(); // blur

    expect(
      screen.queryByText(/is required|must contain at least one letter or number/i)
    ).not.toBeInTheDocument();
    expect(getByHelperText('Your fileset will be created as a-bad-name')).toBeInTheDocument();
  });

  it('shows a local error only after blur when nothing valid survives sanitization', async () => {
    render(<NothingValidToSubmit />);

    const input = screen.getByRole('textbox');
    expect(input).toHaveValue('!!!');
    expect(
      screen.queryByText(/must contain at least one letter or number/i)
    ).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(input);
    await user.tab(); // blur

    expect(
      await screen.findByText(/must contain at least one letter or number/i)
    ).toBeInTheDocument();
  });

  it('checks availability on keystroke and shows "Checking name..." while in flight', async () => {
    render(<WithUniquenessCheck />);

    const user = userEvent.setup();
    await user.type(screen.getByRole('textbox'), 'taken-name');

    expect(await screen.findByText('Checking name...')).toBeInTheDocument();
  });

  it('surfaces the conflict error once the uniqueness check resolves, without needing blur', async () => {
    render(<WithUniquenessCheck />);

    const user = userEvent.setup();
    const input = screen.getByRole('textbox');
    await user.type(input, 'my-fileset');

    expect(
      await screen.findByText('An fileset named my-fileset already exists', {}, { timeout: 2000 })
    ).toBeInTheDocument();
    expect(input).toHaveFocus();
  });
});
