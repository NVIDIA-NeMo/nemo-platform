// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ROUTES } from '@studio/constants/routes';
import { ClaudeCodeChatThread } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeChatThread';
import type {
  ClaudeCodeChatRuntime,
  StudioNavigationRequest,
} from '@studio/routes/agents/ClaudeCodeChatRoute/useClaudeCodeChatRuntime';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { createMemoryRouter, generatePath, RouterProvider } from 'react-router-dom';

const mocks = vi.hoisted(() => ({
  resolveStudioNavigationRequest: vi.fn(),
}));

vi.mock('@assistant-ui/react', () => ({
  AssistantRuntimeProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock('@nemo/common/src/components/AssistantChat/AssistantChatThread', () => ({
  AssistantChatThread: ({
    composerOverride,
    showRunningIndicator,
  }: {
    composerOverride?: ReactNode;
    showRunningIndicator?: boolean;
  }) => (
    <div
      data-testid="assistant-chat-thread"
      data-show-running-indicator={String(showRunningIndicator)}
    >
      {composerOverride}
    </div>
  ),
}));

const WORKSPACE = 'default';
const CHAT_PATH = generatePath(ROUTES.workspace.claudeCodeChat, { workspace: WORKSPACE });

const makeStudioNavigationRequest = (
  overrides?: Partial<StudioNavigationRequest>
): StudioNavigationRequest => ({
  id: 'guardrails:1',
  prompt: 'Add guardrails to an agent',
  suggestion: {
    id: 'guardrails',
    title: 'Open Guardrails',
    description: 'Studio has a UI for managing NeMo Guardrails configurations.',
    href: '/workspaces/default/guardrails',
  },
  ...overrides,
});

const makeChat = (studioNavigationRequest: StudioNavigationRequest | null) =>
  ({
    artifacts: { selections: [], files: [], links: [], tools: [] },
    decisionChoices: [],
    decisionRequest: null,
    decisionStatus: 'pending',
    handleReset: vi.fn(),
    inputRequest: null,
    inputStatus: 'pending',
    isRunning: false,
    loadSession: vi.fn(),
    resolveDecisionRequest: vi.fn(),
    resolveInputRequest: vi.fn(),
    resolveStudioNavigationRequest: mocks.resolveStudioNavigationRequest,
    runtime: {},
    sessionId: null,
    skipDecisionRequest: vi.fn(),
    skipInputRequest: vi.fn(),
    studioNavigationRequest,
    studioNavigationStatus: 'pending',
    submitPrompt: vi.fn(),
  }) as unknown as ClaudeCodeChatRuntime;

const renderThread = (studioNavigationRequest = makeStudioNavigationRequest()) => {
  const router = createMemoryRouter(
    [
      {
        path: ROUTES.workspace.claudeCodeChat,
        element: <ClaudeCodeChatThread chat={makeChat(studioNavigationRequest)} />,
      },
      { path: ROUTES.workspace.guardrails, element: <div data-testid="guardrails-route" /> },
    ],
    { initialEntries: [CHAT_PATH] }
  );

  return render(
    <TestProviders>
      <RouterProvider router={router} />
    </TestProviders>
  );
};

describe('ClaudeCodeChatThread Studio UI navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('offers the matching Studio UI before continuing with Claude Code', () => {
    renderThread();

    expect(screen.getByText('Studio UI available')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /1\.\s+Open Guardrails/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /2\.\s+Continue in chat/i })).toBeInTheDocument();
    expect(screen.getByTestId('assistant-chat-thread')).toHaveAttribute(
      'data-show-running-indicator',
      'false'
    );
  });

  it('resolves with navigate and opens the Studio route', async () => {
    const user = userEvent.setup();
    renderThread();

    await user.click(screen.getByRole('option', { name: /1\.\s+Open Guardrails/i }));

    expect(mocks.resolveStudioNavigationRequest).toHaveBeenCalledWith('navigate');
    expect(await screen.findByTestId('guardrails-route')).toBeInTheDocument();
  });

  it('resolves with continue when the user keeps chatting', async () => {
    const user = userEvent.setup();
    renderThread();

    await user.click(screen.getByRole('option', { name: /2\.\s+Continue in chat/i }));

    expect(mocks.resolveStudioNavigationRequest).toHaveBeenCalledWith('continue');
    expect(screen.queryByTestId('guardrails-route')).not.toBeInTheDocument();
  });
});
