// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SearchBar } from '@studio/components/common/SearchBar/index';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('SearchBar', () => {
  const user = userEvent.setup();

  it('renders with default props', () => {
    render(<SearchBar />);
    expect(screen.getByRole('textbox')).toBeInTheDocument();
  });

  it('renders with custom label', () => {
    const label = 'Search Items';
    render(<SearchBar label={label} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it('calls onSubmit with search value when form is submitted', async () => {
    const onSubmit = vi.fn();
    render(<SearchBar onSubmit={onSubmit} />);

    const input = screen.getByRole('textbox');

    await user.type(input, 'test search');
    await user.keyboard('{Enter}');

    expect(onSubmit).toHaveBeenCalledWith('test search');
  });

  it('resets form when resetOnSubmit is true', async () => {
    const onSubmit = vi.fn();
    render(<SearchBar onSubmit={onSubmit} resetOnSubmit />);

    const input = screen.getByRole('textbox');

    await user.type(input, 'test search');
    await user.keyboard('{Enter}');

    await waitFor(() => expect(input).toHaveValue(''));
  });

  it('does not reset form when resetOnSubmit is false', async () => {
    const onSubmit = vi.fn();
    render(<SearchBar onSubmit={onSubmit} resetOnSubmit={false} />);

    const input = screen.getByRole('textbox');

    await user.type(input, 'test search');
    await user.keyboard('{Enter}');

    expect(input).toHaveValue('test search');
  });
});
