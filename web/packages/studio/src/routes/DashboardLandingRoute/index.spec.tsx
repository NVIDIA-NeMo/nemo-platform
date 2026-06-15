// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ROUTES } from '@studio/constants/routes';
import { DashboardLandingRoute } from '@studio/routes/DashboardLandingRoute';
import { mockFeatureFlags } from '@studio/tests/util/mockFeatureFlags';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, generatePath, RouterProvider, useLocation } from 'react-router';

const mocks = vi.hoisted(() => ({
  listClaudeCodeSkills: vi.fn(),
}));

vi.mock('@studio/routes/agents/ClaudeCodeChatRoute/api', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@studio/routes/agents/ClaudeCodeChatRoute/api')>();

  return {
    ...actual,
    listClaudeCodeHistorySessions: vi.fn(async () => []),
    listClaudeCodeSkills: mocks.listClaudeCodeSkills,
  };
});

const workspace = 'default';
const CHAT_ROUTE_TEST_ID = 'chat-route';

const ChatRouteProbe = () => {
  const location = useLocation();
  const state = location.state as { initialPrompt?: string } | null;

  return (
    <div data-testid={CHAT_ROUTE_TEST_ID}>
      {location.pathname}|{state?.initialPrompt}
    </div>
  );
};

const renderRoute = () => {
  const route = generatePath(ROUTES.workspace.dashboard, { workspace });
  const router = createMemoryRouter(
    [
      { path: ROUTES.workspace.dashboard, element: <DashboardLandingRoute /> },
      { path: ROUTES.workspace.claudeCodeChat, element: <ChatRouteProbe /> },
    ],
    {
      initialEntries: [route],
    }
  );

  return render(
    <TestProviders>
      <RouterProvider router={router} />
    </TestProviders>
  );
};

describe('DashboardLandingRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFeatureFlags({
      agentsEnabled: true,
      guardrailsEnabled: true,
      inferenceProviderEnabled: true,
      safeSynthesizerEnabled: true,
    });
    mocks.listClaudeCodeSkills.mockResolvedValue([
      {
        name: 'nemo-guardrails',
        claude_name: 'nemo-nemo-guardrails',
        description: 'NeMo guardrails CLI reference.',
        source: 'nemo-platform',
        install_path: '.claude/skills/nemo-nemo-guardrails/SKILL.md',
        installed: false,
      },
      {
        name: 'guardrails-plugin',
        claude_name: 'nemo-guardrails-plugin',
        description: 'Guardrails plugin reference.',
        source: 'nemo-guardrails-plugin',
        install_path: '.claude/skills/nemo-guardrails-plugin/SKILL.md',
        installed: false,
      },
      {
        name: 'agents-optimize',
        claude_name: 'nemo-agents-optimize',
        description: 'Optimize a deployed NeMo agent.',
        source: 'nemo-agents-plugin',
        install_path: '.claude/skills/nemo-agents-optimize/SKILL.md',
        installed: false,
      },
      {
        name: 'inference',
        claude_name: 'nemo-inference',
        description: 'Configure inference providers and virtual models.',
        source: 'nemo-platform',
        install_path: '.claude/skills/nemo-inference/SKILL.md',
        installed: false,
      },
      {
        name: 'nemo-build-agent',
        claude_name: 'nemo-nemo-build-agent',
        description: 'Build and deploy a NAT workflow from a spec.',
        source: 'nemo-platform',
        install_path: '.claude/skills/nemo-nemo-build-agent/SKILL.md',
        installed: false,
      },
      {
        name: 'safe-synthesizer',
        claude_name: 'nemo-safe-synthesizer',
        description: 'Generate safety-focused synthetic data.',
        source: 'nemo-platform',
        install_path: '.claude/skills/nemo-safe-synthesizer/SKILL.md',
        installed: false,
      },
    ]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the dashboard landing page', async () => {
    renderRoute();

    expect(await screen.findByText('What would you like to do?')).toBeInTheDocument();
    const composer = screen.getByRole('textbox', { name: 'Message Claude' });
    expect(composer).toBeInTheDocument();
    expect(screen.getByTestId('dashboard-landing-composer')).toHaveClass('rounded-lg');
    expect(screen.getByTestId('dashboard-landing-composer')).not.toHaveClass('rounded-2xl');
    expect(composer).toHaveClass(
      '[&&]:focus:outline-none',
      '[&&]:focus-visible:outline-none',
      '[&&]:focus-visible:ring-0'
    );
    expect(composer).not.toHaveClass('[&&]:focus-visible:outline-accent');
    expect(screen.queryByRole('button', { name: /Explore repo/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Draft a change/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Review recent work/ })).not.toBeInTheDocument();
    expect(
      await screen.findByRole('button', { name: /Add guardrails to an agent/ })
    ).toBeInTheDocument();
    expect(screen.getByTestId('skill-action-card-nemo-guardrails')).toHaveClass(
      'w-72',
      'h-44',
      'flex-none'
    );
    expect(screen.getByRole('button', { name: /Debug guardrails middleware/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Optimize an agent/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Configure inference/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Build an agent/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Generate safety data/ })).toBeInTheDocument();
    expect(
      screen.getAllByTestId('skill-action-skill-name').map((node) => node.textContent)
    ).toEqual(expect.arrayContaining(['nemo-guardrails', 'guardrails-plugin']));
  });

  it('uses a styled native horizontal scrollbar for skill actions', async () => {
    renderRoute();

    await screen.findByRole('button', { name: /Add guardrails to an agent/ });

    const skillActions = screen.getByLabelText('Skill action suggestions');

    expect(skillActions).toHaveClass(
      'overflow-x-auto',
      '[scrollbar-width:thin]',
      '[scrollbar-color:var(--border-color-interaction-base)_var(--background-color-interaction-hover)]',
      '[&::-webkit-scrollbar-thumb]:rounded-full'
    );
    expect(screen.getByTestId('skill-action-row')).toHaveClass('pb-6');
    expect(screen.queryByTestId('skill-action-scrollbar')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Previous skill actions' })
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Next skill actions' })).not.toBeInTheDocument();
  });

  it('requires the skill and related feature flag before showing action cards', async () => {
    mockFeatureFlags({
      agentsEnabled: true,
      evaluatorEnabled: true,
      guardrailsEnabled: false,
      inferenceProviderEnabled: true,
      safeSynthesizerEnabled: false,
    });
    mocks.listClaudeCodeSkills.mockResolvedValue([
      {
        name: 'nemo-guardrails',
        claude_name: 'nemo-nemo-guardrails',
        description: 'NeMo guardrails CLI reference.',
        source: 'nemo-platform',
        install_path: '.claude/skills/nemo-nemo-guardrails/SKILL.md',
        installed: false,
      },
      {
        name: 'inference',
        claude_name: 'nemo-inference',
        description: 'Configure inference providers and virtual models.',
        source: 'nemo-platform',
        install_path: '.claude/skills/nemo-inference/SKILL.md',
        installed: false,
      },
      {
        name: 'safe-synthesizer',
        claude_name: 'nemo-safe-synthesizer',
        description: 'Generate safety-focused synthetic data.',
        source: 'nemo-platform',
        install_path: '.claude/skills/nemo-safe-synthesizer/SKILL.md',
        installed: false,
      },
    ]);

    renderRoute();

    expect(await screen.findByRole('button', { name: /Configure inference/ })).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /Add guardrails to an agent/ })
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Generate safety data/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Run model evaluations/ })).not.toBeInTheDocument();
    expect(screen.queryByTestId('skill-actions-disabled')).not.toBeInTheDocument();
  });

  it('shows a disabled message when every skill is filtered by feature flags', async () => {
    mockFeatureFlags({
      guardrailsEnabled: false,
      inferenceProviderEnabled: false,
      safeSynthesizerEnabled: false,
    });
    mocks.listClaudeCodeSkills.mockResolvedValue([
      {
        name: 'nemo-guardrails',
        claude_name: 'nemo-nemo-guardrails',
        description: 'NeMo guardrails CLI reference.',
        source: 'nemo-platform',
        install_path: '.claude/skills/nemo-nemo-guardrails/SKILL.md',
        installed: false,
      },
      {
        name: 'inference',
        claude_name: 'nemo-inference',
        description: 'Configure inference providers and virtual models.',
        source: 'nemo-platform',
        install_path: '.claude/skills/nemo-inference/SKILL.md',
        installed: false,
      },
    ]);

    renderRoute();

    expect(await screen.findByTestId('skill-actions-disabled')).toBeInTheDocument();
  });

  it('falls back to default action cards when Claude skills fail to load', async () => {
    mocks.listClaudeCodeSkills.mockRejectedValue(new Error('skills unavailable'));

    renderRoute();

    expect(await screen.findByRole('button', { name: /Explore repo/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Draft a change/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Review recent work/ })).toBeInTheDocument();
    expect(screen.queryByText('Could not load Claude skills.')).not.toBeInTheDocument();
    expect(screen.queryByTestId('skill-actions-error')).not.toBeInTheDocument();
  });

  it('shows an empty state when no Claude skills are available', async () => {
    mocks.listClaudeCodeSkills.mockResolvedValue([]);

    renderRoute();

    expect(await screen.findByTestId('skill-actions-empty')).toBeInTheDocument();
    expect(screen.getByText('No skills found')).toBeInTheDocument();
  });

  it('shows a disabled message for skills without curated templates', async () => {
    mocks.listClaudeCodeSkills.mockResolvedValue([
      {
        name: 'custom-plugin-skill',
        claude_name: 'nemo-custom-plugin-skill',
        description: 'A plugin-specific workflow.',
        source: 'custom-plugin',
        install_path: '.claude/skills/nemo-custom-plugin-skill/SKILL.md',
        installed: false,
      },
    ]);

    renderRoute();

    expect(await screen.findByTestId('skill-actions-disabled')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Custom Plugin Skill/ })).not.toBeInTheDocument();
  });

  it('lets skill action cards populate the landing composer', async () => {
    const user = userEvent.setup();
    renderRoute();

    await user.click(await screen.findByRole('button', { name: /Add guardrails to an agent/ }));

    expect(
      screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Message Claude' }).value
    ).toContain('add input and output guardrails');
  });

  it('only enables the send affordance once the composer has text', async () => {
    const user = userEvent.setup();
    renderRoute();

    const composer = await screen.findByRole('textbox', { name: 'Message Claude' });
    const sendButton = screen.getByRole('button', { name: 'Send message' });

    expect(sendButton).toBeDisabled();

    await user.type(composer, 'Sketch a dashboard');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Send message' })).toBeEnabled();
    });
  });

  it('navigates to Claude Code chat with the submitted prompt', async () => {
    const user = userEvent.setup();
    renderRoute();

    await user.type(await screen.findByRole('textbox', { name: 'Message Claude' }), 'Check repo');
    await user.click(screen.getByRole('button', { name: 'Send message' }));

    expect(await screen.findByTestId(CHAT_ROUTE_TEST_ID)).toHaveTextContent(
      `${generatePath(ROUTES.workspace.claudeCodeChat, { workspace })}|Check repo`
    );
  });

  it('submits the landing composer when Enter is pressed', async () => {
    const user = userEvent.setup();
    renderRoute();

    await user.type(await screen.findByRole('textbox', { name: 'Message Claude' }), 'Check repo');
    await user.keyboard('{Enter}');

    expect(await screen.findByTestId(CHAT_ROUTE_TEST_ID)).toHaveTextContent(
      `${generatePath(ROUTES.workspace.claudeCodeChat, { workspace })}|Check repo`
    );
  });

  it('keeps Shift Enter as a new line in the landing composer', async () => {
    const user = userEvent.setup();
    renderRoute();

    const composer = await screen.findByRole('textbox', { name: 'Message Claude' });

    await user.type(composer, 'Line one');
    await user.keyboard('{Shift>}{Enter}{/Shift}');
    await user.type(composer, 'Line two');

    expect(screen.queryByTestId(CHAT_ROUTE_TEST_ID)).not.toBeInTheDocument();
    expect(composer).toHaveValue('Line one\nLine two');
  });
});
