// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getCopilotActiveSessionStorageKey } from '@studio/routes/agents/CopilotChatRoute/activeSessionStorage';
import { CopilotSessionNotFoundError } from '@studio/routes/agents/CopilotChatRoute/api';
import { CopilotChatProvider } from '@studio/routes/agents/CopilotChatRoute/context/CopilotChatProvider';
import { useCopilotChatContext } from '@studio/routes/agents/CopilotChatRoute/context/useCopilotChatContext';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';

const mocks = vi.hoisted(() => ({
  applySession: vi.fn(),
  handleReset: vi.fn(),
  getCopilotSessionHistory: vi.fn(),
  sessionId: null as string | null,
  toastError: vi.fn(),
}));

vi.mock('@nemo/common/src/providers/toast/useToast', () => ({
  useToast: () => ({ error: mocks.toastError }),
}));

vi.mock('@studio/routes/agents/CopilotChatRoute/api', async (importOriginal) => ({
  ...(await importOriginal()),
  getCopilotSessionHistory: mocks.getCopilotSessionHistory,
}));

vi.mock('@studio/routes/agents/CopilotChatRoute/util', () => ({
  getCopilotHistoryMessages: () => [],
}));

vi.mock('@studio/routes/agents/CopilotChatRoute/useCopilotChatRuntime', () => ({
  useCopilotChatRuntime: () => ({
    loadSession: mocks.applySession,
    handleReset: mocks.handleReset,
    sessionId: mocks.sessionId,
  }),
}));

const WORKSPACE = 'default';

const LoadButton = () => {
  const { loadSession, startNewChat } = useCopilotChatContext();
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
      <CopilotChatProvider workspace={WORKSPACE}>{children}</CopilotChatProvider>
    </MemoryRouter>
  );

describe('CopilotChatProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mocks.sessionId = null;
  });

  it('fetches history and loads it into the runtime on loadSession', async () => {
    mocks.getCopilotSessionHistory.mockResolvedValue({
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
    mocks.getCopilotSessionHistory.mockReturnValue(
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
    localStorage.setItem(getCopilotActiveSessionStorageKey(WORKSPACE), 'session-1');
    mocks.getCopilotSessionHistory.mockResolvedValue({
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
    const storageKey = getCopilotActiveSessionStorageKey(WORKSPACE);
    localStorage.setItem(storageKey, 'missing-session');
    mocks.getCopilotSessionHistory.mockRejectedValue(
      new CopilotSessionNotFoundError('no such session history')
    );

    renderProvider(<div />);

    await waitFor(() => expect(localStorage.getItem(storageKey)).toBeNull());
    expect(mocks.applySession).not.toHaveBeenCalled();
    expect(mocks.toastError).not.toHaveBeenCalled();
  });
});
