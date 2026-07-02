// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ClaudeCodeToolCallPart } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeToolCallPart';
import {
  CLAUDE_CODE_JOB_PROGRESS_MCP_TOOL_NAME,
  CLAUDE_CODE_JOB_PROGRESS_TOOL_NAME,
} from '@studio/routes/agents/ClaudeCodeChatRoute/jobProgressConsts';
import {
  CLAUDE_CODE_COLLAPSED_STUDIO_DETAILS_TOOL_NAME,
  CLAUDE_CODE_COLLAPSED_THINKING_TOOL_NAME,
  CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME,
} from '@studio/routes/agents/ClaudeCodeChatRoute/toolParts';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@studio/routes/agents/ClaudeCodeChatRoute/JobProgressToolCall', () => ({
  JobProgressToolCall: ({ args }: { args: Record<string, unknown> }) => (
    <div data-testid="mock-job-progress">{String(args.job_name)}</div>
  ),
}));

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
    'my-density-xs',
    'flex',
    'max-w-full',
    'flex-wrap',
    'items-center',
    'gap-x-density-sm',
    'gap-y-density-xs',
    'rounded',
    'border',
    'border-base',
    'border-l-2',
    'border-l-[var(--border-color-accent-blue)]',
    'bg-[color-mix(in_srgb,var(--background-color-accent-blue-subtle)_38%,var(--background-color-surface-base))]',
    'px-density-sm',
    'py-density-xs',
    'text-secondary'
  );
  expect(subtleBlock).not.toHaveClass('claude-code-tool-call-running');
  expect(subtleBlock).not.toHaveClass('bg-gray-050', 'dark:bg-gray-900');
  expect(screen.getByTestId('claude-code-tool-call-subtle-action')).toHaveClass('basis-full');
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

const expectFileChangeBlockFullWidth = () => {
  expect(screen.getByTestId('claude-code-tool-call-file-change')).toHaveClass(
    'w-full',
    'max-w-full'
  );
};

describe('ClaudeCodeToolCallPart', () => {
  it('renders Studio summary details behind a worked-for disclosure', async () => {
    const user = userEvent.setup();

    render(
      <ClaudeCodeToolCallPart
        addResult={vi.fn()}
        args={{
          label: 'worked for 42s',
          parts: [
            {
              type: 'text',
              text: [
                '## Optimization report',
                '',
                '**Current config:** `meta-llama-3-1-70b-instruct`',
                '',
                '- Preserved first suggestion',
                '- Preserved second suggestion',
              ].join('\n'),
            },
            {
              type: 'tool-call',
              args: { command: 'pwd' },
              argsText: '{"command":"pwd"}',
              toolCallId: 'toolu_bash',
              toolName: 'Bash',
            },
          ],
        }}
        argsText=""
        resume={vi.fn()}
        status={{ type: 'complete' }}
        toolCallId="claude-code-collapsed-studio-details"
        toolName={CLAUDE_CODE_COLLAPSED_STUDIO_DETAILS_TOOL_NAME}
        type="tool-call"
      />
    );

    const disclosure = screen.getByTestId('claude-code-collapsed-studio-details');
    expect(disclosure).toHaveTextContent('worked for 42s');
    expect(disclosure).not.toHaveAttribute('open');
    expect(screen.getByTestId('claude-code-collapsed-studio-details-content')).toHaveTextContent(
      'Optimization report'
    );
    expect(screen.getByTestId('claude-code-collapsed-studio-details-content')).toHaveTextContent(
      'Ran pwd'
    );

    await user.click(screen.getByText('worked for 42s'));

    expect(disclosure).toHaveAttribute('open');
    expect(screen.getByRole('heading', { level: 2, name: 'Optimization report' })).toBeVisible();
    expect(screen.getByText('Current config:')).toHaveProperty('tagName', 'STRONG');
    expect(screen.getByText('meta-llama-3-1-70b-instruct')).toHaveProperty('tagName', 'CODE');
    expect(screen.getAllByRole('listitem')[0]).toHaveTextContent('Preserved first suggestion');
  });

  it('renders collapsed thinking as an expandable subtle disclosure', async () => {
    const user = userEvent.setup();

    render(
      <ClaudeCodeToolCallPart
        addResult={vi.fn()}
        args={{
          text: 'I will inspect the repo first.\n\nI found the files that matter.',
        }}
        argsText='{"text":"I will inspect the repo first.\\n\\nI found the files that matter."}'
        resume={vi.fn()}
        status={{ type: 'complete' }}
        toolCallId="claude-code-collapsed-thinking"
        toolName={CLAUDE_CODE_COLLAPSED_THINKING_TOOL_NAME}
        type="tool-call"
      />
    );

    const disclosure = screen.getByTestId('claude-code-collapsed-thinking');
    expect(disclosure).toHaveTextContent('Earlier thinking');
    expect(disclosure).not.toHaveAttribute('open');

    await user.click(screen.getByText('Earlier thinking'));

    expect(disclosure).toHaveAttribute('open');
    expect(screen.getByTestId('claude-code-collapsed-thinking-content')).toHaveTextContent(
      'I will inspect the repo first.'
    );
    expect(screen.getByTestId('claude-code-collapsed-thinking-content')).toHaveTextContent(
      'I found the files that matter.'
    );
  });

  it('replaces a persisted unknown work time with a neutral label', () => {
    render(
      <ClaudeCodeToolCallPart
        addResult={vi.fn()}
        args={{
          label: 'worked for unknown',
          parts: [{ type: 'text', text: 'Completed work.' }],
        }}
        argsText=""
        resume={vi.fn()}
        status={{ type: 'complete' }}
        toolCallId="claude-code-collapsed-studio-details"
        toolName={CLAUDE_CODE_COLLAPSED_STUDIO_DETAILS_TOOL_NAME}
        type="tool-call"
      />
    );

    expect(screen.getByText('Work details')).toBeVisible();
    expect(screen.queryByText('worked for unknown')).not.toBeInTheDocument();
  });

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

  it('renders grouped subtle tool calls in a single block with each action on its own line', () => {
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
    const subtleActions = screen.getAllByTestId('claude-code-tool-call-subtle-action');
    expect(subtleActions).toHaveLength(3);
    for (const action of subtleActions) {
      expect(action).toHaveClass('basis-full');
    }
    expect(screen.getAllByTestId('claude-code-tool-call-subtle-icon')).toHaveLength(3);
    expect(screen.queryAllByTestId('claude-code-tool-call-subtle')).toHaveLength(1);
    expect(screen.queryByTestId('claude-code-tool-call')).not.toBeInTheDocument();
  });

  it('summarizes repeated grouped tool actions with expandable details', async () => {
    const user = userEvent.setup();

    render(
      <ClaudeCodeToolCallPart
        addResult={vi.fn()}
        args={{
          actions: [
            {
              args: { command: 'pwd', description: 'check working directory' },
              toolCallId: 'toolu_bash_1',
              toolName: 'Bash',
            },
            {
              args: { command: 'ls', description: 'list files' },
              toolCallId: 'toolu_bash_2',
              toolName: 'Bash',
            },
            {
              args: { command: 'git status', description: 'check git status' },
              toolCallId: 'toolu_bash_3',
              toolName: 'Bash',
            },
            {
              args: { command: 'pnpm test', description: 'run tests' },
              toolCallId: 'toolu_bash_4',
              toolName: 'Bash',
            },
            { args: { command: 'pnpm typecheck' }, toolCallId: 'toolu_bash_5', toolName: 'Bash' },
            { args: { file_path: 'README.md' }, toolCallId: 'toolu_read_1', toolName: 'Read' },
            {
              args: { file_path: 'package.json' },
              toolCallId: 'toolu_read_2',
              toolName: 'Read',
            },
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
    expect(subtleBlock).toHaveTextContent('Ran 5 commands');
    expect(subtleBlock).toHaveTextContent('Read 2 files');
    expect(subtleBlock).toHaveAttribute(
      'title',
      expect.stringContaining('Ran check working directory')
    );
    expect(subtleBlock).toHaveAttribute('title', expect.stringContaining('Read README.md'));
    expect(screen.getAllByTestId('claude-code-tool-call-subtle-action')).toHaveLength(2);
    expect(screen.getAllByTestId('claude-code-tool-call-subtle-icon')).toHaveLength(2);
    expect(screen.getAllByTestId('claude-code-tool-call-subtle-details')).toHaveLength(2);
    for (const details of screen.getAllByTestId('claude-code-tool-call-subtle-details')) {
      expect(details).toHaveClass('basis-full');
    }
    expect(screen.queryByTestId('claude-code-tool-call')).not.toBeInTheDocument();

    const commandDetails = screen.getAllByTestId('claude-code-tool-call-subtle-details')[0]!;
    expect(commandDetails).not.toHaveAttribute('open');

    await user.click(screen.getByText('Ran 5 commands'));

    expect(commandDetails).toHaveAttribute('open');
    expect(
      within(commandDetails)
        .getAllByTestId('claude-code-tool-call-subtle-detail-item')
        .map((item) => item.textContent)
    ).toEqual([
      'check working directory',
      'list files',
      'check git status',
      'run tests',
      'pnpm typecheck',
    ]);
    expect(screen.getAllByTestId('claude-code-tool-call-subtle-detail-item')).toHaveLength(7);
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

  it('animates subtle tool text while the tool call is running', () => {
    render(
      <ClaudeCodeToolCallPart
        addResult={vi.fn()}
        args={{ command: 'pwd', description: 'check the working directory' }}
        argsText='{"command":"pwd","description":"check the working directory"}'
        resume={vi.fn()}
        status={{ type: 'running' }}
        toolCallId="toolu_running_bash"
        toolName="Bash"
        type="tool-call"
      />
    );

    expect(screen.getByTestId('claude-code-tool-call-subtle')).toHaveClass(
      'claude-code-tool-call-running'
    );
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

    expectFileChangeBlockFullWidth();
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

  it('animates file change text while the tool call is running', () => {
    render(
      <ClaudeCodeToolCallPart
        addResult={vi.fn()}
        args={{
          content: 'export const value = 1;\n',
          file_path: 'web/packages/studio/src/routes/agents/NewFile.tsx',
        }}
        argsText='{"file_path":"web/packages/studio/src/routes/agents/NewFile.tsx","content":"export const value = 1;\\n"}'
        resume={vi.fn()}
        status={{ type: 'running' }}
        toolCallId="toolu_running_write"
        toolName="Write"
        type="tool-call"
      />
    );

    expect(screen.getByText('Wrote 1 file')).toHaveClass('claude-code-tool-call-running');
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

    expectFileChangeBlockFullWidth();
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

  it.each([CLAUDE_CODE_JOB_PROGRESS_TOOL_NAME, CLAUDE_CODE_JOB_PROGRESS_MCP_TOOL_NAME])(
    'renders %s as a rich job progress tool call',
    (toolName) => {
      render(
        <ClaudeCodeToolCallPart
          addResult={vi.fn()}
          args={{ job_name: 'studio-job-1' }}
          argsText='{"job_name":"studio-job-1"}'
          resume={vi.fn()}
          status={{ type: 'complete' }}
          toolCallId="toolu_job"
          toolName={toolName}
          type="tool-call"
        />
      );

      expect(screen.getByTestId('mock-job-progress')).toHaveTextContent('studio-job-1');
      expect(screen.queryByTestId('claude-code-tool-call-subtle')).not.toBeInTheDocument();
    }
  );
});
