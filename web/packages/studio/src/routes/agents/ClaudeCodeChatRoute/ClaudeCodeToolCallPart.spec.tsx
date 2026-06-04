// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ClaudeCodeToolCallPart } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeToolCallPart';
import { CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME } from '@studio/routes/agents/ClaudeCodeChatRoute/toolParts';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

interface SubtleToolCase {
  readonly args: Record<string, string>;
  readonly expectedText: string;
  readonly toolName: string;
}

const subtleToolCases: SubtleToolCase[] = [
  {
    args: { command: 'pwd', description: 'check the working directory' },
    expectedText: 'Ran check the working directory',
    toolName: 'Bash',
  },
  {
    args: { question: 'Do you want to continue?' },
    expectedText: 'Asked Do you want to continue?',
    toolName: 'AskUserQuestion',
  },
  {
    args: { query: 'ClaudeCodeToolCallPart' },
    expectedText: 'Searched files ClaudeCodeToolCallPart',
    toolName: 'FindFiles',
  },
  {
    args: { pattern: 'ClaudeCodeToolCallPart' },
    expectedText: 'Searched text ClaudeCodeToolCallPart',
    toolName: 'Grep',
  },
  {
    args: { task: 'check the route' },
    expectedText: 'Created task check the route',
    toolName: 'TaskCreate',
  },
  {
    args: { status: 'in_progress' },
    expectedText: 'Updated task in_progress',
    toolName: 'TaskUpdate',
  },
  {
    args: { query: 'read files' },
    expectedText: 'Searched tools read files',
    toolName: 'ToolSearch',
  },
];

const expectSubtleToolBlock = (subtleBlock: HTMLElement) => {
  expect(subtleBlock).toHaveClass(
    'my-0.5',
    'flex',
    'max-w-full',
    'flex-wrap',
    'items-center',
    'gap-x-density-sm',
    'gap-y-0.5',
    'text-gray-400',
    'dark:text-gray-600'
  );
  expect(subtleBlock).not.toHaveClass('bg-gray-050', 'dark:bg-gray-900');
  expect(screen.getByTestId('claude-code-tool-call-subtle-action')).toBeInTheDocument();
  expect(screen.getByTestId('claude-code-tool-call-subtle-icon')).toBeInTheDocument();
};

const expectLineChangeColors = ({
  additions,
  deletions,
}: {
  additions: string;
  deletions: string;
}) => {
  for (const addition of screen.getAllByText(additions)) {
    expect(addition).toHaveClass('text-feedback-success');
  }
  for (const deletion of screen.getAllByText(deletions)) {
    expect(deletion).toHaveClass('text-feedback-danger');
  }
};

describe('ClaudeCodeToolCallPart', () => {
  it.each(subtleToolCases)(
    'renders $toolName as subtle text',
    ({ args, expectedText, toolName }) => {
      render(
        <ClaudeCodeToolCallPart
          addResult={vi.fn()}
          args={args}
          argsText={JSON.stringify(args)}
          resume={vi.fn()}
          status={{ type: 'complete' }}
          toolCallId={`toolu_${toolName}`}
          toolName={toolName}
          type="tool-call"
        />
      );

      const subtleBlock = screen.getByTestId('claude-code-tool-call-subtle');
      expect(subtleBlock).toHaveTextContent(expectedText);
      expect(subtleBlock).toHaveAttribute('title', expectedText);
      expectSubtleToolBlock(subtleBlock);
      expect(screen.queryByTestId('claude-code-tool-call')).not.toBeInTheDocument();
    }
  );

  it('renders grouped subtle tool calls in a single row', () => {
    render(
      <ClaudeCodeToolCallPart
        addResult={vi.fn()}
        args={{
          actions: [
            { args: { command: 'pwd' }, toolCallId: 'toolu_bash', toolName: 'Bash' },
            {
              args: { file_path: 'web/packages/studio/src/App.tsx' },
              toolCallId: 'toolu_read',
              toolName: 'Read',
            },
            { args: { pattern: 'TODO' }, toolCallId: 'toolu_grep', toolName: 'Grep' },
          ],
        }}
        argsText=""
        resume={vi.fn()}
        status={{ type: 'complete' }}
        toolCallId="toolu_group"
        toolName={CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME}
        type="tool-call"
      />
    );

    const subtleBlock = screen.getByTestId('claude-code-tool-call-subtle');
    expect(subtleBlock).toHaveTextContent('Ran pwd');
    expect(subtleBlock).toHaveTextContent('Read App.tsx');
    expect(subtleBlock).toHaveTextContent('Searched text TODO');
    expect(subtleBlock).toHaveAttribute('title', 'Ran pwd | Read App.tsx | Searched text TODO');
    expect(screen.getAllByTestId('claude-code-tool-call-subtle-action')).toHaveLength(3);
    expect(screen.getAllByTestId('claude-code-tool-call-subtle-icon')).toHaveLength(3);
    expect(screen.queryAllByTestId('claude-code-tool-call-subtle')).toHaveLength(1);
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
    expectSubtleToolBlock(readBlock);
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
    expectLineChangeColors({ additions: '+2', deletions: '-0' });
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
    expectLineChangeColors({ additions: '+1', deletions: '-1' });
  });

  it('renders known non-file-change tool calls as subtle text by default', () => {
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

    const subtleBlock = screen.getByTestId('claude-code-tool-call-subtle');
    expect(subtleBlock).toHaveTextContent('Found files **/*.tsx');
    expectSubtleToolBlock(subtleBlock);
    expect(screen.queryByTestId('claude-code-tool-call')).not.toBeInTheDocument();
  });

  it('renders unknown tool calls as subtle text by default', () => {
    render(
      <ClaudeCodeToolCallPart
        addResult={vi.fn()}
        args={{ query: 'symbols' }}
        argsText='{"query":"symbols"}'
        resume={vi.fn()}
        status={{ type: 'complete' }}
        toolCallId="toolu_unknown"
        toolName="InspectWorkspace"
        type="tool-call"
      />
    );

    const subtleBlock = screen.getByTestId('claude-code-tool-call-subtle');
    expect(subtleBlock).toHaveTextContent('Used InspectWorkspace symbols');
    expectSubtleToolBlock(subtleBlock);
    expect(screen.queryByTestId('claude-code-tool-call')).not.toBeInTheDocument();
  });
});
