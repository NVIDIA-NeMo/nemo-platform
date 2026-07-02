// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ROUTES } from '@studio/constants/routes';
import { ClaudeCodeChatRoute } from '@studio/routes/agents/ClaudeCodeChatRoute';
import type { ClaudeCodeChatLoadStatus } from '@studio/routes/agents/ClaudeCodeChatRoute/context/useClaudeCodeChatContext';
import type { ClaudeCodeChatRouteState } from '@studio/routes/agents/ClaudeCodeChatRoute/types';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { generatePath, MemoryRouter, Route, Routes } from 'react-router-dom';

const mocks = vi.hoisted(() => ({
  chat: {
    artifacts: { selections: [], files: [], links: [], tools: [] },
    sessionId: null as string | null,
    submitPrompt: vi.fn(),
  },
  loadStatus: 'idle' as ClaudeCodeChatLoadStatus,
  loadSession: vi.fn(),
  startNewChat: vi.fn(),
}));

vi.mock('@studio/hooks/useWorkspaceFromPath', () => ({
  useWorkspaceFromPath: () => 'default',
}));

vi.mock('@studio/providers/breadcrumbs/useBreadcrumbs', () => ({
  useBreadcrumbs: vi.fn(),
}));

vi.mock('@studio/routes/agents/ClaudeCodeChatRoute/context/useClaudeCodeChatContext', () => ({
  useClaudeCodeChatContext: () => ({
    chat: mocks.chat,
    loadStatus: mocks.loadStatus,
    loadSession: mocks.loadSession,
    startNewChat: mocks.startNewChat,
  }),
}));

vi.mock('@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeChatThread', () => ({
  ClaudeCodeChatThread: () => <div data-testid="chat-thread" />,
}));

vi.mock('@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeLayout', () => ({
  ClaudeCodeLayout: ({
    activeSessionId,
    children,
    onNewChat,
  }: {
    activeSessionId?: string;
    children: ReactNode;
    onNewChat?: () => void;
  }) => (
    <div data-active-session-id={activeSessionId ?? ''} data-testid="chat-layout">
      <button type="button" onClick={onNewChat}>
        new chat
      </button>
      {children}
    </div>
  ),
}));

const WORKSPACE = 'default';
const CHAT_PATH = generatePath(ROUTES.workspace.claudeCodeChat, { workspace: WORKSPACE });

const renderClaudeCodeChatRoute = (options?: {
  search?: string;
  state?: ClaudeCodeChatRouteState;
}) =>
  render(
    <MemoryRouter
      initialEntries={[{ pathname: CHAT_PATH, search: options?.search, state: options?.state }]}
    >
      <Routes>
        <Route path={ROUTES.workspace.claudeCodeChat} element={<ClaudeCodeChatRoute />} />
      </Routes>
    </MemoryRouter>
  );

describe('ClaudeCodeChatRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.chat.sessionId = null;
    mocks.chat.submitPrompt = vi.fn();
    mocks.loadStatus = 'idle';
  });

  it('starts a dashboard prompt in a fresh session without loading a session', async () => {
    renderClaudeCodeChatRoute({ state: { initialPrompt: ' Check repo ' } });

    await waitFor(() => expect(mocks.startNewChat).toHaveBeenCalled());
    await waitFor(() => expect(mocks.chat.submitPrompt).toHaveBeenCalledWith('Check repo'));
    expect(mocks.loadSession).not.toHaveBeenCalled();
  });

  it('does not submit a dashboard prompt to an existing session before the reset completes', async () => {
    // The bug: startNewChat() calls setSessionId(null) which is a React state update.
    // If submitPrompt is called in the same synchronous block, ensureSessionId still
    // holds the old session ID in its closure and the prompt goes to the wrong session.
    mocks.chat.sessionId = 'old-session';

    renderClaudeCodeChatRoute({ state: { initialPrompt: 'Hello' } });

    await waitFor(() => expect(mocks.startNewChat).toHaveBeenCalled());
    // submitPrompt must NOT have been called yet — it should be deferred until
    // sessionId becomes null (handled by the second effect).
    expect(mocks.chat.submitPrompt).not.toHaveBeenCalled();
  });

  it('does not trigger a session load when initialPrompt clears a ?session= param', async () => {
    // The race: Effect 1 preserving ?session= in the navigate call lets the
    // session-load effect see selectedSessionId = 'old' + sessionId = null on the
    // next render and call loadSession, conflicting with startNewChat.
    renderClaudeCodeChatRoute({
      search: '?session=old-session',
      state: { initialPrompt: 'Hello' },
    });

    await waitFor(() => expect(mocks.startNewChat).toHaveBeenCalled());
    expect(mocks.loadSession).not.toHaveBeenCalled();
  });

  it('loads the session selected via the session query param', async () => {
    renderClaudeCodeChatRoute({ search: '?session=session-existing' });

    await waitFor(() => expect(mocks.loadSession).toHaveBeenCalledWith('session-existing'));
    expect(mocks.chat.submitPrompt).not.toHaveBeenCalled();
  });

  it('shows the loading state immediately when a session is selected but not yet loaded', () => {
    // loadStatus starts 'idle' — the effect hasn't fired yet. The old chat must not
    // flash before the spinner appears.
    mocks.loadStatus = 'idle';
    mocks.chat.sessionId = null;

    renderClaudeCodeChatRoute({ search: '?session=session-existing' });

    expect(screen.getByText('Loading chat...')).toBeInTheDocument();
  });

  it('shows the loading state while the selected session is loading', () => {
    mocks.loadStatus = 'loading';
    mocks.chat.sessionId = null;

    renderClaudeCodeChatRoute({ search: '?session=session-existing' });

    expect(screen.getByText('Loading chat...')).toBeInTheDocument();
  });

  it('resets the shared runtime when New Chat is used from the history panel', async () => {
    mocks.chat.sessionId = 'session-existing';

    renderClaudeCodeChatRoute({ search: '?session=session-existing' });
    await userEvent.setup().click(screen.getByRole('button', { name: 'new chat' }));

    expect(mocks.startNewChat).toHaveBeenCalledOnce();
  });

  it('renders the chat for the active session once loaded', () => {
    mocks.chat.sessionId = 'session-existing';

    renderClaudeCodeChatRoute({ search: '?session=session-existing' });

    expect(screen.getByTestId('chat-thread')).toBeInTheDocument();
    expect(screen.getByTestId('chat-layout')).toHaveAttribute(
      'data-active-session-id',
      'session-existing'
    );
  });
});
