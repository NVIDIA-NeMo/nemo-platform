// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ClaudeCodeReasoningPart } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeReasoningPart';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('ClaudeCodeReasoningPart', () => {
  it('renders completed thinking collapsed and expandable', async () => {
    const user = userEvent.setup();

    render(
      <ClaudeCodeReasoningPart
        status={{ type: 'complete' }}
        text="checking the repo"
        type="reasoning"
      />
    );

    const thinkingBlock = screen.getByTestId('claude-code-thinking-block');
    expect(thinkingBlock).not.toHaveAttribute('open');

    await user.click(screen.getByText('Thinking'));

    expect(thinkingBlock).toHaveAttribute('open');
  });

  it('renders running thinking open', () => {
    render(
      <ClaudeCodeReasoningPart
        status={{ type: 'running' }}
        text="still checking"
        type="reasoning"
      />
    );

    expect(screen.getByTestId('claude-code-thinking-block')).toHaveAttribute('open');
  });
});
