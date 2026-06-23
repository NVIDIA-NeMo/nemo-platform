// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getClaudeCodeActiveSessionStorageKey } from '@studio/routes/agents/ClaudeCodeChatRoute/activeSessionStorage';
import { ClaudeCodeChatProvider } from '@studio/routes/agents/ClaudeCodeChatRoute/context/ClaudeCodeChatProvider';
import { useClaudeCodeChatContext } from '@studio/routes/agents/ClaudeCodeChatRoute/context/useClaudeCodeChatContext';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';

const mocks = vi.hoisted(() => ({
  applySession: vi.fn(),
  handleReset: vi.fn(),
  getClaudeCodeSessionHistory: vi.fn(),
  sessionId: null as string | null,
}));

vi.mock('@nemo/common/src/providers/toast/useToast', () => ({
  useToast: () => ({ error: vi.fn() }),
}));

vi.mock('@studio/routes/agents/ClaudeCodeChatRoute/api', () => ({
  getClaudeCodeSessionHistory: mocks.getClaudeCodeSessionHistory,
}));

vi.mock('@studio/routes/agents/ClaudeCodeChatRoute/util', () => ({
  getClaudeCodeHistoryMessages: () => [],
}));

vi.mock('@studio/routes/agents/ClaudeCodeChatRoute/useClaudeCodeChatRuntime', () => ({
  useClaudeCodeChatRuntime: () => ({
    loadSession: mocks.applySession,
    handleReset: mocks.handleReset,
    sessionId: mocks.sessionId,
  }),
}));

const WORKSPACE = 'default';

const LoadButton = () => {
  const { loadSession } = useClaudeCodeChatContext();
  return (
    <button type="button" onClick={() => loadSession('session-2')}>
      load
    </button>
  );
};

const renderProvider = (children: ReactNode = <LoadButton />) =>
  render(
    <MemoryRouter initialEntries={[`/workspaces/${WORKSPACE}/jobs`]}>
      <ClaudeCodeChatProvider workspace={WORKSPACE}>{children}</ClaudeCodeChatProvider>
    </MemoryRouter>
  );

describe('ClaudeCodeChatProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mocks.sessionId = null;
  });

  it('fetches history and loads it into the runtime on loadSession', async () => {
    mocks.getClaudeCodeSessionHistory.mockResolvedValue({
      session_id: 'session-2',
      items: [],
      chat_artifacts: { selections: [], files: [], links: [], tools: [] },
    });

    renderProvider();
    await userEvent.click(screen.getByText('load'));

    await waitFor(() =>
      expect(mocks.applySession).toHaveBeenCalledWith(
        expect.objectContaining({ sessionId: 'session-2' })
      )
    );
  });

  it('hydrates the stored active session on mount', async () => {
    localStorage.setItem(getClaudeCodeActiveSessionStorageKey(WORKSPACE), 'session-1');
    mocks.getClaudeCodeSessionHistory.mockResolvedValue({
      session_id: 'session-1',
      items: [],
      chat_artifacts: { selections: [], files: [], links: [], tools: [] },
    });

    renderProvider(<div />);

    await waitFor(() =>
      expect(mocks.applySession).toHaveBeenCalledWith(
        expect.objectContaining({ sessionId: 'session-1' })
      )
    );
  });
});
