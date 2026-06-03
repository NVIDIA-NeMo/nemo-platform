// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ClaudeCodeToolCallPart } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeToolCallPart';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('ClaudeCodeToolCallPart', () => {
  it('omits Bash tool calls from the chat thread', () => {
    const { container } = render(
      <ClaudeCodeToolCallPart
        addResult={vi.fn()}
        args={{ command: 'pwd', description: 'check the working directory' }}
        argsText='{"command":"pwd","description":"check the working directory"}'
        resume={vi.fn()}
        status={{ type: 'complete' }}
        toolCallId="toolu_1"
        toolName="Bash"
        type="tool-call"
      />
    );

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId('claude-code-tool-call-subtle')).not.toBeInTheDocument();
    expect(screen.queryByTestId('claude-code-tool-call')).not.toBeInTheDocument();
  });

  it('renders Read as subtle text with only the file name', () => {
    render(
      <ClaudeCodeToolCallPart
        addResult={vi.fn()}
        args={{ file_path: 'web/packages/studio/src/App.tsx' }}
        argsText='{"file_path":"web/packages/studio/src/App.tsx"}'
        resume={vi.fn()}
        status={{ type: 'complete' }}
        toolCallId="toolu_2"
        toolName="Read"
        type="tool-call"
      />
    );

    const readBlock = screen.getByTestId('claude-code-tool-call-subtle');
    expect(readBlock).toHaveTextContent('Read App.tsx');
    expect(readBlock.tagName).toBe('DIV');
    expect(readBlock).toHaveClass('block', 'w-full', 'text-secondary');
    expect(screen.queryByText('web/packages/studio/src/App.tsx')).not.toBeInTheDocument();
  });

  it('renders other tool-use rows with expandable input', async () => {
    const user = userEvent.setup();

    render(
      <ClaudeCodeToolCallPart
        addResult={vi.fn()}
        args={{ pattern: 'ClaudeCodeToolCallPart' }}
        argsText='{"pattern":"ClaudeCodeToolCallPart"}'
        resume={vi.fn()}
        status={{ type: 'complete' }}
        toolCallId="toolu_3"
        toolName="Grep"
        type="tool-call"
      />
    );

    const toolCall = screen.getByTestId('claude-code-tool-call');
    expect(toolCall).not.toHaveAttribute('open');
    expect(screen.getByText('Search text')).toBeInTheDocument();
    expect(screen.getByText('ClaudeCodeToolCallPart')).toBeInTheDocument();

    await user.click(screen.getByText('Search text'));

    expect(toolCall).toHaveAttribute('open');
    expect(screen.getByText('Input')).toBeInTheDocument();
    expect(screen.getByText('{"pattern":"ClaudeCodeToolCallPart"}')).toBeInTheDocument();
  });
});
