// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CreateFilesetStart } from '@studio/components/CreateFilesetStart';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const renderStart = () => {
  const onContinue = vi.fn();
  render(<CreateFilesetStart onContinue={onContinue} />);
  return { onContinue };
};

describe('CreateFilesetStart', () => {
  it('renders all start options', () => {
    renderStart();

    expect(screen.getByText('Describe with AI')).toBeInTheDocument();
    expect(screen.getByText('Start from a template')).toBeInTheDocument();
    expect(screen.getByText('Build from scratch')).toBeInTheDocument();
  });

  it('shows no Continue footer until an option is chosen', () => {
    renderStart();

    expect(screen.queryByRole('button', { name: /continue/i })).not.toBeInTheDocument();
  });

  it('does not select disabled options (they are no-ops)', async () => {
    const user = userEvent.setup();
    const { onContinue } = renderStart();

    await user.click(screen.getByText('Describe with AI'));

    expect(screen.queryByRole('button', { name: /continue/i })).not.toBeInTheDocument();
    expect(onContinue).not.toHaveBeenCalled();
  });

  it('selecting Build from scratch reveals Continue and invokes onContinue with "scratch"', async () => {
    const user = userEvent.setup();
    const { onContinue } = renderStart();

    await user.click(screen.getByText('Build from scratch'));

    const continueButton = screen.getByRole('button', { name: /continue/i });
    expect(continueButton).toBeEnabled();

    await user.click(continueButton);
    expect(onContinue).toHaveBeenCalledTimes(1);
    expect(onContinue).toHaveBeenCalledWith({ optionId: 'scratch' });
  });

  it('reveals template cards but keeps Continue disabled until a template is chosen', async () => {
    const user = userEvent.setup();
    renderStart();

    await user.click(screen.getByText('Start from a template'));

    expect(screen.getByText('Instruction fine-tuning (SFT)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /continue/i })).toBeDisabled();
    expect(screen.getByText('Pick a recipe to continue.')).toBeInTheDocument();
  });

  it('choosing a template enables Continue and invokes onContinue with the template id', async () => {
    const user = userEvent.setup();
    const { onContinue } = renderStart();

    await user.click(screen.getByText('Start from a template'));
    await user.click(screen.getByText('Instruction fine-tuning (SFT)'));

    await user.click(screen.getByRole('button', { name: /continue/i }));

    expect(onContinue).toHaveBeenCalledTimes(1);
    expect(onContinue).toHaveBeenCalledWith({
      optionId: 'template',
      templateId: 'sft-instruction',
    });
  });

  it('switching options clears a prior template selection', async () => {
    const user = userEvent.setup();
    renderStart();

    await user.click(screen.getByText('Start from a template'));
    await user.click(screen.getByText('Instruction fine-tuning (SFT)'));
    expect(screen.getByRole('button', { name: /continue/i })).toBeEnabled();

    await user.click(screen.getByText('Build from scratch'));
    await user.click(screen.getByText('Start from a template'));

    // Template selection was reset when the option changed, so Continue is blocked again.
    expect(screen.getByRole('button', { name: /continue/i })).toBeDisabled();
  });
});
