// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AddColumnPalette } from '@studio/components/AddColumnPalette';
import { render, screen, waitFor } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';

describe('AddColumnPalette', () => {
  it('renders the header and grouped column types', () => {
    render(<AddColumnPalette />);

    expect(screen.getByText('Add a column')).toBeInTheDocument();
    // Sampler is its own group, with every sub-type broken out.
    expect(screen.getByText('Sampler')).toBeInTheDocument();
    expect(screen.getByText('Generate')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /UUID/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Person/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /LLM-Text/ })).toBeInTheDocument();
  });

  it('calls onAddColumn with the sampler type for a sampler card', async () => {
    const user = userEvent.setup();
    const onAddColumn = vi.fn();
    render(<AddColumnPalette onAddColumn={onAddColumn} />);

    await user.click(screen.getByRole('button', { name: /Category/ }));

    expect(onAddColumn).toHaveBeenCalledWith({
      columnType: 'sampler',
      samplerType: 'category',
    });
  });

  it('calls onAddColumn with just the column type for a non-sampler card', async () => {
    const user = userEvent.setup();
    const onAddColumn = vi.fn();
    render(<AddColumnPalette onAddColumn={onAddColumn} />);

    await user.click(screen.getByRole('button', { name: /LLM-Judge/ }));

    expect(onAddColumn).toHaveBeenCalledWith({
      columnType: 'llm-judge',
      samplerType: undefined,
    });
  });

  it('activates an option by keyboard', async () => {
    const user = userEvent.setup();
    const onAddColumn = vi.fn();
    render(<AddColumnPalette onAddColumn={onAddColumn} />);

    screen.getByRole('button', { name: /Expression/ }).focus();
    await user.keyboard('{Enter}');

    expect(onAddColumn).toHaveBeenCalledWith({
      columnType: 'expression',
      samplerType: undefined,
    });
  });

  it('filters options by the search query', async () => {
    const user = userEvent.setup();
    render(<AddColumnPalette />);

    await user.type(screen.getByLabelText('Search column types'), 'gaussian');

    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /UUID/ })).not.toBeInTheDocument()
    );
    expect(screen.getByRole('button', { name: /Gaussian/ })).toBeInTheDocument();
  });

  it('shows an empty state when nothing matches', async () => {
    const user = userEvent.setup();
    render(<AddColumnPalette />);

    await user.type(screen.getByLabelText('Search column types'), 'zzzzz');

    expect(await screen.findByText(/No column types match/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /UUID/ })).not.toBeInTheDocument();
  });
});
