// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getAssistantActiveSessionStorageKey } from '@studio/routes/agents/AssistantChatRoute/activeSessionStorage';
import { AssistantSessionNotFoundError } from '@studio/routes/agents/AssistantChatRoute/api';
import { AssistantChatProvider } from '@studio/routes/agents/AssistantChatRoute/context/AssistantChatProvider';
import { useAssistantChatContext } from '@studio/routes/agents/AssistantChatRoute/context/useAssistantChatContext';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';

const mocks = vi.hoisted(() => ({
  applySession: vi.fn(),
  handleReset: vi.fn(),
  getAssistantSessionHistory: vi.fn(),
  sessionId: null as string | null,
  toastError: vi.fn(),
}));

vi.mock('@nemo/common/src/providers/toast/useToast', () => ({
  useToast: () => ({ error: mocks.toastError }),
}));

vi.mock('@studio/routes/agents/AssistantChatRoute/api', async (importOriginal) => ({
  ...(await importOriginal()),
  getAssistantSessionHistory: mocks.getAssistantSessionHistory,
}));

vi.mock('@studio/routes/agents/AssistantChatRoute/util', () => ({
  getAssistantHistoryMessages: () => [],
}));

vi.mock('@studio/routes/agents/AssistantChatRoute/useAssistantChatRuntime', () => ({
  useAssistantChatRuntime: () => ({
    loadSession: mocks.applySession,
    handleReset: mocks.handleReset,
    sessionId: mocks.sessionId,
  }),
}));

const WORKSPACE = 'default';

const LoadButton = () => {
  const { loadSession, startNewChat } = useAssistantChatContext();
  return (
    <>
      <button type="button" onClick={() => loadSession('session-2')}>
        load
      </button>
      <button type="button" onClick={startNewChat}>
        new
      </button>
    </>
  );
};

const renderProvider = (children: ReactNode = <LoadButton />) =>
  render(
    <MemoryRouter initialEntries={[`/workspaces/${WORKSPACE}/jobs`]}>
      <AssistantChatProvider workspace={WORKSPACE}>{children}</AssistantChatProvider>
    </MemoryRouter>
  );

describe('AssistantChatProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mocks.sessionId = null;
  });

  it('fetches history and loads it into the runtime on loadSession', async () => {
    mocks.getAssistantSessionHistory.mockResolvedValue({
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

  it('cancels a pending session load when a new chat is started', async () => {
    let resolveHistory: ((value: unknown) => void) | undefined;
    mocks.getAssistantSessionHistory.mockReturnValue(
      new Promise((resolve) => {
        resolveHistory = resolve;
      })
    );

    renderProvider();
    const user = userEvent.setup();

    await user.click(screen.getByText('load'));
    await user.click(screen.getByText('new'));

    // The load resolves after the reset; it must not rehydrate the old session.
    resolveHistory?.({
      session_id: 'session-2',
      items: [],
      chat_artifacts: { selections: [], files: [], links: [], tools: [] },
    });

    await waitFor(() => expect(mocks.handleReset).toHaveBeenCalled());
    expect(mocks.applySession).not.toHaveBeenCalled();
  });

  it('hydrates the stored active session on mount', async () => {
    localStorage.setItem(getAssistantActiveSessionStorageKey(WORKSPACE), 'session-1');
    mocks.getAssistantSessionHistory.mockResolvedValue({
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

  it('forgets a stored active session when its history no longer exists', async () => {
    const storageKey = getAssistantActiveSessionStorageKey(WORKSPACE);
    localStorage.setItem(storageKey, 'missing-session');
    mocks.getAssistantSessionHistory.mockRejectedValue(
      new AssistantSessionNotFoundError('no such session history')
    );

    renderProvider(<div />);

    await waitFor(() => expect(localStorage.getItem(storageKey)).toBeNull());
    expect(mocks.applySession).not.toHaveBeenCalled();
    expect(mocks.toastError).not.toHaveBeenCalled();
  });
});
