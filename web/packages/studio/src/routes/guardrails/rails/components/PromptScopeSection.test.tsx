// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PromptScopeSection } from '@studio/routes/guardrails/rails/components/PromptScopeSection';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { type FC, useState } from 'react';

interface InitialValues {
  maxTokens?: number;
  maxLength?: number;
  stop?: string[];
}

/**
 * `PromptScopeSection` is a controlled component, so the harness owns state the same way a
 * real caller (`SelfCheckSettings`) does — through props, never internally. Only the initial
 * values are configurable; every interaction flows back in through the harness's own state,
 * exactly as it would through a `RailsConfig` draft.
 */
const mountSection = (initial: InitialValues = {}) => {
  const Harness: FC = () => {
    const [maxTokens, setMaxTokens] = useState(initial.maxTokens);
    const [maxLength, setMaxLength] = useState(initial.maxLength);
    const [stop, setStop] = useState<string[]>(initial.stop ?? []);

    return (
      <TestProviders>
        <PromptScopeSection
          scope="input"
          enabled
          onEnabledChange={() => {}}
          prompt=""
          onPromptChange={() => {}}
          variables={[]}
          maxTokens={maxTokens}
          onMaxTokensChange={setMaxTokens}
          maxLength={maxLength}
          onMaxLengthChange={setMaxLength}
          stop={stop}
          onStopChange={setStop}
        />
      </TestProviders>
    );
  };

  render(<Harness />);
};

describe('PromptScopeSection', () => {
  it('reports the typed max tokens as a number', async () => {
    const user = userEvent.setup();
    mountSection();

    await user.type(screen.getByRole('spinbutton', { name: 'Input Prompt Max Tokens' }), '256');

    expect(screen.getByRole('spinbutton', { name: 'Input Prompt Max Tokens' })).toHaveValue(256);
  });

  it('clearing max tokens reports undefined, not zero or an empty string', async () => {
    const user = userEvent.setup();
    mountSection({ maxTokens: 256 });

    const input = screen.getByRole('spinbutton', { name: 'Input Prompt Max Tokens' });
    await user.clear(input);

    expect(input).toHaveValue(null);
  });

  it('reports the typed max prompt length as a number', async () => {
    const user = userEvent.setup();
    mountSection();

    await user.type(
      screen.getByRole('spinbutton', { name: 'Input Prompt Max Prompt Length' }),
      '8000'
    );

    expect(screen.getByRole('spinbutton', { name: 'Input Prompt Max Prompt Length' })).toHaveValue(
      8000
    );
  });

  it('adds a stop sequence on Enter and clears the draft input', async () => {
    const user = userEvent.setup();
    mountSection();

    const input = screen.getByPlaceholderText('Add a stop sequence and press Enter');
    await user.type(input, 'STOP{Enter}');

    expect(screen.getByText('STOP')).toBeInTheDocument();
    expect(input).toHaveValue('');
  });

  it('does not add a duplicate or blank stop sequence', async () => {
    const user = userEvent.setup();
    mountSection({ stop: ['STOP'] });

    const input = screen.getByPlaceholderText('Add a stop sequence and press Enter');
    await user.type(input, 'STOP{Enter}');
    await user.type(input, '   {Enter}');

    expect(screen.getAllByText('STOP')).toHaveLength(1);
  });

  it('removes a stop sequence when its tag is clicked', async () => {
    const user = userEvent.setup();
    mountSection({ stop: ['STOP', 'END'] });

    await user.click(screen.getByRole('button', { name: 'Remove stop sequence STOP' }));

    expect(screen.queryByText('STOP')).not.toBeInTheDocument();
    expect(screen.getByText('END')).toBeInTheDocument();
  });
});
