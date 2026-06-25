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

  it('renders history and skills segmented controls', () => {
    render(
      <ClaudeCodeHistoryPanel
        activeSessionId="session-1"
        onNewChat={vi.fn()}
        onSelectSession={vi.fn()}
      />
    );

    expect(screen.getByRole('radio', { name: 'History' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'Skills' })).not.toBeChecked();
    expect(screen.getByRole('button', { name: 'New chat' })).toBeInTheDocument();
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

    render(
      <ClaudeCodeHistoryPanel
        activeSessionId="session-1"
        onNewChat={onNewChat}
        onSelectSession={onSelectSession}
      />
    );

    expect(await screen.findByText('Review the latest agent work')).toBeInTheDocument();
    expect(screen.getByText('Bash')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'New chat' }));
    expect(onNewChat).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('button', { name: /Review the latest agent work/ }));
    expect(onSelectSession).toHaveBeenCalledWith('session-1');
  });

  it('renders job artifacts as Studio links', () => {
    render(
      <ClaudeCodeHistoryPanel
        activeSessionId="session-1"
        artifacts={{
          workspace: 'default',
          selections: [],
          files: [],
          links: [],
          jobs: [
            {
              name: 'agent-eval-1',
              job_type: 'agent_evaluation',
              source: 'evaluator',
            },
          ],
          tools: [],
        }}
        onNewChat={vi.fn()}
        onSelectSession={vi.fn()}
      />
    );

    expect(screen.getByText('Jobs')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /agent-eval-1/ })).toHaveAttribute(
      'href',
      '/workspaces/default/agents/evaluations/agent-eval-1'
    );
  });

  it('lists Claude Code skills in the skills tab', async () => {
    const user = userEvent.setup();
    render(
      <ClaudeCodeHistoryPanel
        activeSessionId="session-1"
        onNewChat={vi.fn()}
        onSelectSession={vi.fn()}
      />
    );

    await user.click(screen.getByRole('radio', { name: 'Skills' }));

    expect(await screen.findByText('Inference')).toBeInTheDocument();
    expect(screen.getByText('Use NeMo Platform inference.')).toBeInTheDocument();
    expect(screen.getByText('nemo-inference')).toBeInTheDocument();
    expect(screen.queryByText('Source: nemo-platform')).not.toBeInTheDocument();
    expect(screen.queryByText(/Skill file:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Claude file:/)).not.toBeInTheDocument();
  });
});
