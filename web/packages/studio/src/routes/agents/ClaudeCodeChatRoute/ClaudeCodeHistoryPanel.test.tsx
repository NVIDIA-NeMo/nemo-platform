// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ClaudeCodeHistoryPanel } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeHistoryPanel';
import { render, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';

const mocks = vi.hoisted(() => ({
  listClaudeCodeHistorySessions: vi.fn(),
  listClaudeCodeSkills: vi.fn(),
}));

vi.mock('@studio/routes/agents/ClaudeCodeChatRoute/api', () => ({
  CLAUDE_CODE_HISTORY_SESSIONS_QUERY_KEY: ['claude-code', 'history', 'sessions'],
  CLAUDE_CODE_SKILLS_QUERY_KEY: ['claude-code', 'skills'],
  listClaudeCodeHistorySessions: mocks.listClaudeCodeHistorySessions,
  listClaudeCodeSkills: mocks.listClaudeCodeSkills,
}));

describe('ClaudeCodeHistoryPanel', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    mocks.listClaudeCodeHistorySessions.mockResolvedValue([]);
    mocks.listClaudeCodeSkills.mockResolvedValue([
      {
        name: 'inference',
        claude_name: 'nemo-inference',
        description: 'Use NeMo Platform inference.',
        source: 'nemo-platform',
        source_path: 'packages/nemo_platform_ext/src/nemo_platform_ext/skills/inference',
        install_path: '.claude/skills/nemo-inference/SKILL.md',
        installed: false,
      },
    ]);
  });

  it('starts history and skills collapsed and expands them independently', async () => {
    const user = userEvent.setup();
    render(
      <ClaudeCodeHistoryPanel
        activeSessionId="session-1"
        onNewChat={vi.fn()}
        onSelectSession={vi.fn()}
      />
    );

    const historyButton = screen.getByRole('button', { name: 'Expand All Chats' });
    const skillsButton = screen.getByRole('button', { name: 'Expand Skills' });
    expect(historyButton).toHaveAttribute('aria-expanded', 'false');
    expect(skillsButton).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('button', { name: 'New chat' })).not.toBeInTheDocument();

    await user.click(historyButton);

    expect(screen.getByRole('button', { name: 'Collapse All Chats' })).toHaveAttribute(
      'aria-expanded',
      'true'
    );
    expect(skillsButton).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByRole('button', { name: 'New chat' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'All Chats' })).toHaveClass('min-h-0', 'flex-1');
    expect(screen.getByRole('region', { name: 'Skills' })).toHaveClass('shrink-0');

    await user.click(skillsButton);

    expect(screen.getByRole('button', { name: 'Expand All Chats' })).toHaveAttribute(
      'aria-expanded',
      'false'
    );
    expect(screen.getByRole('button', { name: 'Collapse Skills' })).toHaveAttribute(
      'aria-expanded',
      'true'
    );
    expect(screen.queryByRole('button', { name: 'New chat' })).not.toBeInTheDocument();
  });

  it('renders history sessions and keeps selection working', async () => {
    const user = userEvent.setup();
    const onNewChat = vi.fn();
    const onSelectSession = vi.fn();
    mocks.listClaudeCodeHistorySessions.mockResolvedValue([
      {
        session_id: 'session-1',
        mtime: Date.now() / 1000,
        first_prompt: 'Review the latest agent work',
        message_count: 2,
        token_count: 100,
        tool_call_count: 1,
        tool_calls: ['Bash'],
        chat_artifacts: {
          selections: [],
          files: [],
          links: [],
          jobs: [],
          tools: [],
        },
      },
    ]);

    const { unmount } = render(
      <ClaudeCodeHistoryPanel
        activeSessionId="session-1"
        onNewChat={onNewChat}
        onSelectSession={onSelectSession}
      />
    );

    await user.click(screen.getByRole('button', { name: 'Expand All Chats' }));

    expect(await screen.findByText('Review the latest agent work')).toBeInTheDocument();
    expect(screen.getByText('Bash')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'New chat' }));
    expect(onNewChat).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('button', { name: /Review the latest agent work/ }));
    expect(onSelectSession).toHaveBeenCalledWith('session-1');

    unmount();
    render(
      <ClaudeCodeHistoryPanel
        activeSessionId="session-1"
        onNewChat={onNewChat}
        onSelectSession={onSelectSession}
      />
    );

    expect(screen.getByRole('button', { name: 'Collapse All Chats' })).toHaveAttribute(
      'aria-expanded',
      'true'
    );
  });

  it('shows the summarized title while preserving the full first prompt in the tooltip', async () => {
    const user = userEvent.setup();
    const firstPrompt = 'I want to create an agent that does spam detection for incoming email.';
    mocks.listClaudeCodeHistorySessions.mockResolvedValue([
      {
        session_id: 'session-1',
        mtime: Date.now() / 1000,
        title: 'Create Spam Detector Agent',
        first_prompt: firstPrompt,
        message_count: 2,
        token_count: 100,
        tool_call_count: 0,
        tool_calls: [],
        chat_artifacts: {
          selections: [],
          files: [],
          links: [],
          jobs: [],
          tools: [],
        },
      },
    ]);

    render(
      <ClaudeCodeHistoryPanel
        activeSessionId="session-1"
        onNewChat={vi.fn()}
        onSelectSession={vi.fn()}
      />
    );

    await user.click(screen.getByRole('button', { name: 'Expand All Chats' }));

    const sessionButton = await screen.findByRole('button', {
      name: 'Create Spam Detector Agent now',
    });

    expect(sessionButton).toHaveAttribute('title', expect.stringContaining(firstPrompt));
    expect(screen.queryByText(firstPrompt)).not.toBeInTheDocument();
  });

  it('renders job artifacts as Studio links', () => {
    render(
      <ClaudeCodeHistoryPanel
        activeSessionId="session-1"
        artifacts={{
          workspace: 'default',
          selections: [{ label: 'Environment', value: 'production' }],
          files: [{ action: 'Wrote', path: 'agents/beach-finder.yml' }],
          links: [],
          jobs: [
            {
              name: 'agent-eval-1',
              job_type: 'agent_evaluation',
              source: 'evaluator',
            },
          ],
          tools: ['Bash'],
        }}
        onNewChat={vi.fn()}
        onSelectSession={vi.fn()}
      />
    );

    expect(screen.getByText('Jobs')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Chat artifacts' })).toHaveClass(
      'overflow-hidden',
      'rounded',
      'border',
      'shrink-0',
      'bg-surface-base',
      'dark:bg-surface-raised'
    );
    expect(screen.queryByText('Workspace')).not.toBeInTheDocument();
    expect(screen.getByText('beach-finder.yml')).toBeInTheDocument();
    expect(screen.getAllByRole('separator')).toHaveLength(3);
    expect(screen.getByRole('link', { name: /agent-eval-1/ })).toHaveAttribute(
      'href',
      '/workspaces/default/agents/evaluations/agent-eval-1'
    );
  });

  it('does not treat workspace metadata as a visible chat artifact', () => {
    render(
      <ClaudeCodeHistoryPanel
        activeSessionId="session-1"
        artifacts={{
          workspace: 'default',
          selections: [],
          files: [],
          links: [],
          jobs: [],
          tools: [],
        }}
        onNewChat={vi.fn()}
        onSelectSession={vi.fn()}
      />
    );

    expect(screen.queryByText('Workspace')).not.toBeInTheDocument();
    expect(screen.getByText('No artifacts yet')).toBeInTheDocument();
  });

  it('omits empty artifact sections and their dividers', () => {
    render(
      <ClaudeCodeHistoryPanel
        activeSessionId="session-1"
        artifacts={{
          selections: [],
          files: [],
          links: [],
          jobs: [{ name: 'agent-eval-1' }],
          tools: ['Bash'],
        }}
        onNewChat={vi.fn()}
        onSelectSession={vi.fn()}
      />
    );

    expect(screen.queryByText('Selections')).not.toBeInTheDocument();
    expect(screen.getByText('Jobs')).toBeInTheDocument();
    expect(screen.getByText('Tools')).toBeInTheDocument();
    expect(screen.getAllByRole('separator')).toHaveLength(1);
  });

  it('ignores selections with whitespace-only values', () => {
    render(
      <ClaudeCodeHistoryPanel
        activeSessionId="session-1"
        artifacts={{
          selections: [{ label: 'Environment', value: ' ' }],
          files: [],
          links: [],
          jobs: [],
          tools: [],
        }}
        onNewChat={vi.fn()}
        onSelectSession={vi.fn()}
      />
    );

    expect(screen.queryByText('Selections')).not.toBeInTheDocument();
    expect(screen.getByText('No artifacts yet')).toBeInTheDocument();
  });

  it('lists Claude Code skills in the expanded skills block', async () => {
    const user = userEvent.setup();
    render(
      <ClaudeCodeHistoryPanel
        activeSessionId="session-1"
        onNewChat={vi.fn()}
        onSelectSession={vi.fn()}
      />
    );

    await user.click(screen.getByRole('button', { name: 'Expand Skills' }));

    expect(await screen.findByText('Inference')).toBeInTheDocument();
    expect(screen.getByText('Use NeMo Platform inference.')).toBeInTheDocument();
    expect(screen.getByText('nemo-inference')).toBeInTheDocument();
    expect(screen.queryByText('Source: nemo-platform')).not.toBeInTheDocument();
    expect(screen.queryByText(/Skill file:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Claude file:/)).not.toBeInTheDocument();
  });
});
