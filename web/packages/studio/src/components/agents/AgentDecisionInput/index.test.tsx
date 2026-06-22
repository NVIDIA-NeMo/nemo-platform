// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AgentDecisionInput } from '@studio/components/agents/AgentDecisionInput';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('AgentDecisionInput', () => {
  const request = {
    id: 'permission-1',
    title: 'Approval required',
    description: 'Agent wants to use Bash: List files in current directory.',
    details: {
      command: 'ls',
    },
  };
  const choices = [
    { id: 'yes', label: 'Yes' },
    { id: 'no', label: 'No' },
    {
      id: 'alternative',
      label: 'Tell the Agent what to do differently',
      input: {
        ariaLabel: 'Alternative instruction',
        placeholder: 'Tell the Agent what to do differently',
      },
    },
  ];

  it('renders indexed choices and request details', () => {
    render(
      <AgentDecisionInput
        request={request}
        choices={choices}
        defaultChoiceId="yes"
        onSubmit={vi.fn()}
      />
    );

    expect(screen.getByText('Approval required')).toBeInTheDocument();
    expect(screen.getByText(/Agent wants to use Bash/)).toBeInTheDocument();
    expect(screen.getByText('ls')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /1\.\s+Yes/i })).toHaveAttribute(
      'aria-selected',
      'true'
    );
    expect(screen.getByRole('option', { name: /2\.\s+No/i })).toBeInTheDocument();
    expect(
      screen.getByRole('option', { name: /3\.\s+Tell the Agent what to do differently/i })
    ).toBeInTheDocument();
  });

  it('submits a clicked choice', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();

    render(
      <AgentDecisionInput
        request={request}
        choices={choices}
        defaultChoiceId="yes"
        onSubmit={onSubmit}
      />
    );

    await user.click(screen.getByRole('option', { name: /2\.\s+No/i }));

    expect(onSubmit).toHaveBeenCalledWith({ id: 'no', label: 'No' });
    expect(screen.queryByRole('button', { name: /Submit/i })).not.toBeInTheDocument();
  });

  it('submits indexed choices with the keyboard', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();

    render(
      <AgentDecisionInput
        request={request}
        choices={choices}
        defaultChoiceId="yes"
        onSubmit={onSubmit}
      />
    );

    screen.getByTestId('agent-decision-input').focus();
    await user.keyboard('2');

    expect(onSubmit).toHaveBeenCalledWith({ id: 'no', label: 'No' });
  });

  it('opens an input for a text choice and submits the entered text with enter', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();

    render(
      <AgentDecisionInput
        request={request}
        choices={choices}
        defaultChoiceId="yes"
        onSubmit={onSubmit}
      />
    );

    await user.click(
      screen.getByRole('option', { name: /3\.\s+Tell the Agent what to do differently/i })
    );

    expect(onSubmit).not.toHaveBeenCalled();

    const input = screen.getByRole('textbox', { name: /Alternative instruction/i });
    await user.type(input, 'Use rg instead{Enter}');

    expect(onSubmit).toHaveBeenCalledWith(
      choices[2],
      expect.objectContaining({ text: 'Use rg instead' })
    );
  });

  it('shows a send button for the text choice and submits the entered text', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();

    render(
      <AgentDecisionInput
        request={request}
        choices={choices}
        defaultChoiceId="yes"
        onSubmit={onSubmit}
      />
    );

    expect(screen.queryByRole('button', { name: /Send alternative instruction/i })).toBeNull();

    await user.click(
      screen.getByRole('option', { name: /3\.\s+Tell the Agent what to do differently/i })
    );

    const sendButton = screen.getByRole('button', { name: /Send alternative instruction/i });
    expect(sendButton).toBeDisabled();

    await user.type(
      screen.getByRole('textbox', { name: /Alternative instruction/i }),
      'Use rg instead'
    );
    await user.click(sendButton);

    expect(onSubmit).toHaveBeenCalledWith(
      choices[2],
      expect.objectContaining({ text: 'Use rg instead' })
    );
  });

  it('opens the text choice with its index without submitting an empty response', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();

    render(
      <AgentDecisionInput
        request={request}
        choices={choices}
        defaultChoiceId="yes"
        onSubmit={onSubmit}
      />
    );

    screen.getByTestId('agent-decision-input').focus();
    await user.keyboard('3');

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole('textbox', { name: /Alternative instruction/i })).toBeInTheDocument();
  });

  it('moves away from the text choice with arrow keys', async () => {
    const user = userEvent.setup();

    render(
      <AgentDecisionInput
        request={request}
        choices={choices}
        defaultChoiceId="yes"
        onSubmit={vi.fn()}
      />
    );

    screen.getByTestId('agent-decision-input').focus();
    await user.keyboard('3');
    await user.keyboard('{ArrowUp}');

    expect(screen.getByRole('option', { name: /2\.\s+No/i })).toHaveAttribute(
      'aria-selected',
      'true'
    );
  });

  it('does not move away from the text choice with horizontal arrow keys', async () => {
    const user = userEvent.setup();

    render(
      <AgentDecisionInput
        request={request}
        choices={choices}
        defaultChoiceId="yes"
        onSubmit={vi.fn()}
      />
    );

    screen.getByTestId('agent-decision-input').focus();
    await user.keyboard('3');
    await user.keyboard('{ArrowLeft}');

    expect(
      screen.getByRole('option', { name: /3\.\s+Tell the Agent what to do differently/i })
    ).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('textbox', { name: /Alternative instruction/i })).toBeInTheDocument();
  });

  it('moves selection with arrow keys', async () => {
    const user = userEvent.setup();

    render(
      <AgentDecisionInput
        request={request}
        choices={choices}
        defaultChoiceId="yes"
        onSubmit={vi.fn()}
      />
    );

    screen.getByTestId('agent-decision-input').focus();
    await user.keyboard('{ArrowDown}');

    expect(screen.getByRole('option', { name: /2\.\s+No/i })).toHaveAttribute(
      'aria-selected',
      'true'
    );
  });

  it('does not move menu selection with horizontal arrow keys', async () => {
    const user = userEvent.setup();

    render(
      <AgentDecisionInput
        request={request}
        choices={choices}
        defaultChoiceId="yes"
        onSubmit={vi.fn()}
      />
    );

    screen.getByTestId('agent-decision-input').focus();
    await user.keyboard('{ArrowRight}');

    expect(screen.getByRole('option', { name: /1\.\s+Yes/i })).toHaveAttribute(
      'aria-selected',
      'true'
    );
  });

  it('submits the selected choice with enter after arrow navigation', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();

    render(
      <AgentDecisionInput
        request={request}
        choices={choices}
        defaultChoiceId="yes"
        onSubmit={onSubmit}
      />
    );

    screen.getByTestId('agent-decision-input').focus();
    await user.keyboard('{ArrowDown}');
    await user.keyboard('{Enter}');

    expect(onSubmit).toHaveBeenCalledWith({ id: 'no', label: 'No' });
  });

  it('calls skip from the bottom action', async () => {
    const user = userEvent.setup();
    const onSkip = vi.fn();

    render(
      <AgentDecisionInput
        request={request}
        choices={choices}
        defaultChoiceId="yes"
        onSubmit={vi.fn()}
        onSkip={onSkip}
      />
    );

    await user.click(screen.getByRole('button', { name: /Skip/i }));

    expect(onSkip).toHaveBeenCalledTimes(1);
  });
});
