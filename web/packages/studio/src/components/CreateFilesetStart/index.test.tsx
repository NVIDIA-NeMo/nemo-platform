// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CreateFilesetStart } from '@studio/components/CreateFilesetStart';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('CreateFilesetStart', () => {
  it('renders all four start options', () => {
    render(<CreateFilesetStart onContinue={vi.fn()} />);

    expect(screen.getByText('Describe with AI')).toBeInTheDocument();
    expect(screen.getByText('Start from a template')).toBeInTheDocument();
    expect(screen.getByText('Build from scratch')).toBeInTheDocument();
  });

  it('shows no Continue footer until a selectable option is chosen', () => {
    render(<CreateFilesetStart onContinue={vi.fn()} />);

    expect(screen.queryByRole('button', { name: /continue/i })).not.toBeInTheDocument();
  });

  it('does not select disabled options (they are no-ops)', async () => {
    const user = userEvent.setup();
    const onContinue = vi.fn();
    render(<CreateFilesetStart onContinue={onContinue} />);

    await user.click(screen.getByText('Describe with AI'));

    expect(screen.queryByRole('button', { name: /continue/i })).not.toBeInTheDocument();
    expect(onContinue).not.toHaveBeenCalled();
  });

  it('selecting Build from scratch reveals Continue and invokes onContinue with "scratch"', async () => {
    const user = userEvent.setup();
    const onContinue = vi.fn();
    render(<CreateFilesetStart onContinue={onContinue} />);

    await user.click(screen.getByText('Build from scratch'));

    const continueButton = screen.getByRole('button', { name: /continue/i });
    expect(continueButton).toBeInTheDocument();

    await user.click(continueButton);
    expect(onContinue).toHaveBeenCalledTimes(1);
    expect(onContinue).toHaveBeenCalledWith('scratch');
  });

  it('reveals template cards but no Continue until a template is chosen', async () => {
    const user = userEvent.setup();
    render(<CreateFilesetStart onContinue={vi.fn()} />);

    await user.click(screen.getByText('Start from a template'));

    expect(screen.getByText('Instruction fine-tuning (SFT)')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /continue/i })).not.toBeInTheDocument();
  });

  it('choosing a template reveals Continue and invokes onContinue with the template id', async () => {
    const user = userEvent.setup();
    const onContinue = vi.fn();
    render(<CreateFilesetStart onContinue={onContinue} />);

    await user.click(screen.getByText('Start from a template'));
    await user.click(screen.getByText('Instruction fine-tuning (SFT)'));

    const continueButton = screen.getByRole('button', { name: /continue/i });
    await user.click(continueButton);

    expect(onContinue).toHaveBeenCalledTimes(1);
    expect(onContinue).toHaveBeenCalledWith('template', 'sft-instruction');
  });

  it('switching options clears a prior template selection', async () => {
    const user = userEvent.setup();
    render(<CreateFilesetStart onContinue={vi.fn()} />);

    await user.click(screen.getByText('Start from a template'));
    await user.click(screen.getByText('Instruction fine-tuning (SFT)'));
    expect(screen.getByRole('button', { name: /continue/i })).toBeInTheDocument();

    await user.click(screen.getByText('Build from scratch'));
    await user.click(screen.getByText('Start from a template'));

    // Template selection was reset when the option changed, so Continue is gone again.
    expect(screen.queryByRole('button', { name: /continue/i })).not.toBeInTheDocument();
  });
});
