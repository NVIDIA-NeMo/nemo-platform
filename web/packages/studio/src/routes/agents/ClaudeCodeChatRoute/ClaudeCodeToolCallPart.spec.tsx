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

  it('omits TaskUpdate tool calls from the chat thread', () => {
    const { container } = render(
      <ClaudeCodeToolCallPart
        addResult={vi.fn()}
        args={{ status: 'in_progress' }}
        argsText='{"status":"in_progress"}'
        resume={vi.fn()}
        status={{ type: 'complete' }}
        toolCallId="toolu_task"
        toolName="TaskUpdate"
        type="tool-call"
      />
    );

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId('claude-code-tool-call-subtle')).not.toBeInTheDocument();
    expect(screen.queryByTestId('claude-code-tool-call')).not.toBeInTheDocument();
  });

  it('omits Grep tool calls from the chat thread', () => {
    const { container } = render(
      <ClaudeCodeToolCallPart
        addResult={vi.fn()}
        args={{ pattern: 'ClaudeCodeToolCallPart' }}
        argsText='{"pattern":"ClaudeCodeToolCallPart"}'
        resume={vi.fn()}
        status={{ type: 'complete' }}
        toolCallId="toolu_grep"
        toolName="Grep"
        type="tool-call"
      />
    );

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText('Search text')).not.toBeInTheDocument();
    expect(screen.queryByTestId('claude-code-tool-call-subtle')).not.toBeInTheDocument();
    expect(screen.queryByTestId('claude-code-tool-call')).not.toBeInTheDocument();
  });

  it('omits AskUserQuestion tool calls from the chat thread', () => {
    const { container } = render(
      <ClaudeCodeToolCallPart
        addResult={vi.fn()}
        args={{ question: 'Do you want to continue?' }}
        argsText='{"question":"Do you want to continue?"}'
        resume={vi.fn()}
        status={{ type: 'complete' }}
        toolCallId="toolu_question"
        toolName="AskUserQuestion"
        type="tool-call"
      />
    );

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText('AskUserQuestion')).not.toBeInTheDocument();
    expect(screen.queryByTestId('claude-code-tool-call-subtle')).not.toBeInTheDocument();
    expect(screen.queryByTestId('claude-code-tool-call')).not.toBeInTheDocument();
  });

  it.each(['FindFiles', 'TaskCreate', 'ToolSearch'])(
    'omits %s tool calls from the chat thread',
    (toolName) => {
      const { container } = render(
        <ClaudeCodeToolCallPart
          addResult={vi.fn()}
          args={{ query: 'ClaudeCodeToolCallPart' }}
          argsText='{"query":"ClaudeCodeToolCallPart"}'
          resume={vi.fn()}
          status={{ type: 'complete' }}
          toolCallId={`toolu_${toolName}`}
          toolName={toolName}
          type="tool-call"
        />
      );

      expect(container).toBeEmptyDOMElement();
      expect(screen.queryByText(toolName)).not.toBeInTheDocument();
      expect(screen.queryByTestId('claude-code-tool-call-subtle')).not.toBeInTheDocument();
      expect(screen.queryByTestId('claude-code-tool-call')).not.toBeInTheDocument();
    }
  );

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
    expect(readBlock).toHaveClass('my-0.5', 'block', 'w-full', 'text-secondary');
    expect(screen.queryByText('web/packages/studio/src/App.tsx')).not.toBeInTheDocument();
  });

  it('renders Write as a file change summary with expandable content', async () => {
    const user = userEvent.setup();

    render(
      <ClaudeCodeToolCallPart
        addResult={vi.fn()}
        args={{
          content: 'export const value = 1;\nexport const next = 2;\n',
          file_path: 'web/packages/studio/src/routes/agents/NewFile.tsx',
        }}
        argsText='{"file_path":"web/packages/studio/src/routes/agents/NewFile.tsx","content":"export const value = 1;\\nexport const next = 2;\\n"}'
        resume={vi.fn()}
        status={{ type: 'complete' }}
        toolCallId="toolu_write"
        toolName="Write"
        type="tool-call"
      />
    );

    expect(screen.getByTestId('claude-code-tool-call-file-change')).toBeInTheDocument();
    const details = screen.getByTestId('claude-code-tool-call-file-change-details');

    expect(screen.getByText('Wrote 1 file')).toBeInTheDocument();
    expect(
      screen.getByText('web/packages/studio/src/routes/agents/NewFile.tsx')
    ).toBeInTheDocument();
    expect(screen.getAllByText('+2')).toHaveLength(2);
    expect(screen.getAllByText('-0')).toHaveLength(2);
    expect(details).not.toHaveAttribute('open');

    await user.click(screen.getByText('Review'));

    expect(details).toHaveAttribute('open');
    expect(screen.getByTestId('claude-code-tool-call-file-change-review-surface')).toHaveClass(
      'bg-gray-050',
      'dark:bg-gray-900'
    );
    expect(screen.getByTestId('claude-code-tool-call-file-change-review')).toHaveTextContent(
      'export const value = 1; export const next = 2;'
    );
  });

  it('renders Edit as a file change summary with edited stats', () => {
    render(
      <ClaudeCodeToolCallPart
        addResult={vi.fn()}
        args={{
          file_path: 'web/packages/studio/src/routes/agents/ExistingFile.tsx',
          new_string: 'const label = "new";\n',
          old_string: 'const label = "old";\n',
        }}
        argsText='{"file_path":"web/packages/studio/src/routes/agents/ExistingFile.tsx","old_string":"const label = \"old\";\\n","new_string":"const label = \"new\";\\n"}'
        resume={vi.fn()}
        status={{ type: 'complete' }}
        toolCallId="toolu_edit"
        toolName="Edit"
        type="tool-call"
      />
    );

    expect(screen.getByTestId('claude-code-tool-call-file-change')).toBeInTheDocument();
    expect(screen.getByText('Edited 1 file')).toBeInTheDocument();
    expect(
      screen.getByText('web/packages/studio/src/routes/agents/ExistingFile.tsx')
    ).toBeInTheDocument();
    expect(screen.getAllByText('+1')).toHaveLength(2);
    expect(screen.getAllByText('-1')).toHaveLength(2);
  });

  it('renders other tool-use rows with expandable input', async () => {
    const user = userEvent.setup();

    render(
      <ClaudeCodeToolCallPart
        addResult={vi.fn()}
        args={{ pattern: '**/*.tsx' }}
        argsText='{"pattern":"**/*.tsx"}'
        resume={vi.fn()}
        status={{ type: 'complete' }}
        toolCallId="toolu_3"
        toolName="Glob"
        type="tool-call"
      />
    );

    const toolCall = screen.getByTestId('claude-code-tool-call');
    expect(toolCall).not.toHaveAttribute('open');
    expect(screen.getByText('Find files')).toBeInTheDocument();
    expect(screen.getByText('**/*.tsx')).toBeInTheDocument();

    await user.click(screen.getByText('Find files'));

    expect(toolCall).toHaveAttribute('open');
    expect(screen.getByText('Input')).toBeInTheDocument();
    expect(screen.getByTestId('claude-code-tool-call-input-surface')).toHaveClass(
      'bg-gray-050',
      'dark:bg-gray-900'
    );
    expect(screen.getByText('{"pattern":"**/*.tsx"}')).toBeInTheDocument();
  });
});
