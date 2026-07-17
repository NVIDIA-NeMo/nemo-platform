// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AgentPanel } from '@studio/components/sidePanels/AgentPanels/AgentPanel';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { server } from '@studio/mocks/node';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router-dom';

// These match mock agent names in handlers.ts
const MOCK_AGENT_WITH_DEPLOYMENTS = 'react-agent'; // has rag-agent-prod (running) + sql-agent-dev (stopped)
const MOCK_AGENT_WITH_ERROR_DEPLOYMENT = 'react-agent2'; // has chat-agent-staging (error)
const MOCK_AGENT_UNKNOWN = 'unknown-agent';

const renderPanel = (agentName?: string, open = true) =>
  render(
    <TestProviders>
      <MemoryRouter>
        <AgentPanel agentName={agentName} workspace="default" open={open} onOpenChange={vi.fn()} />
      </MemoryRouter>
    </TestProviders>
  );

describe('AgentPanel', () => {
  describe('when closed', () => {
    it('renders nothing visible when open is false', () => {
      renderPanel(MOCK_AGENT_WITH_DEPLOYMENTS, false);
      expect(
        screen.queryByRole('heading', { name: MOCK_AGENT_WITH_DEPLOYMENTS })
      ).not.toBeInTheDocument();
    });
  });

  describe('tabs', () => {
    it('renders Details and Chat Playground tabs', () => {
      renderPanel(MOCK_AGENT_WITH_DEPLOYMENTS);

      expect(screen.getByRole('radio', { name: 'Details' })).toBeInTheDocument();
      expect(screen.getByRole('radio', { name: 'Chat Playground' })).toBeInTheDocument();
    });

    it('defaults to Details tab', () => {
      renderPanel(MOCK_AGENT_WITH_DEPLOYMENTS);

      expect(screen.getByRole('radio', { name: 'Details' })).toBeChecked();
    });

    it('switches to Chat Playground when the tab is clicked', async () => {
      const user = userEvent.setup();
      renderPanel(MOCK_AGENT_WITH_DEPLOYMENTS);

      await user.click(screen.getByRole('radio', { name: 'Chat Playground' }));

      // AssistantChat renders a composer with this aria-label when the chat playground mounts.
      expect(await screen.findByRole('textbox', { name: /Task prompt/i })).toBeInTheDocument();
    });
  });

  describe('details tab', () => {
    it('renders the agent name as the panel heading', () => {
      renderPanel(MOCK_AGENT_WITH_DEPLOYMENTS);
      expect(
        screen.getByRole('heading', { name: MOCK_AGENT_WITH_DEPLOYMENTS })
      ).toBeInTheDocument();
    });

    it('renders agent name and workspace in the Agent Details accordion', async () => {
      renderPanel(MOCK_AGENT_WITH_DEPLOYMENTS);

      // Wait for data to load by checking config_format (only appears after agents query resolves)
      expect(await screen.findByText('nat-workflow-v1', {}, { timeout: 5000 })).toBeInTheDocument();
      expect(screen.getByText('default')).toBeInTheDocument();
    });

    it('renders the agent model from config.llms', async () => {
      renderPanel(MOCK_AGENT_WITH_DEPLOYMENTS);

      expect(
        await screen.findByText('meta-llama-3-1-70b-instruct', {}, { timeout: 5000 })
      ).toBeInTheDocument();
    });

    it('renders a non-empty description when present', async () => {
      renderPanel(MOCK_AGENT_WITH_ERROR_DEPLOYMENT);

      // react-agent2 has description "Second react agent" (appears in title area + KVPair)
      const items = await screen.findAllByText('Second react agent', {}, { timeout: 5000 });
      expect(items.length).toBeGreaterThan(0);
    });

    describe('Deployments accordion', () => {
      it('shows deployments for the agent', async () => {
        renderPanel(MOCK_AGENT_WITH_DEPLOYMENTS);

        expect(await screen.findByText('rag-agent-prod')).toBeInTheDocument();
        expect(screen.getByText('sql-agent-dev')).toBeInTheDocument();
      });

      it('shows deployment status badges', async () => {
        renderPanel(MOCK_AGENT_WITH_DEPLOYMENTS);

        // StatusBadge renders the capitalized label from the badge map.
        // `stopped` is not a real AgentDeploymentStatus, so it falls through to `Unknown`.
        expect(await screen.findByText('Running')).toBeInTheDocument();
        expect(screen.getByText('Unknown')).toBeInTheDocument();
      });

      it('shows empty state when agent has no matching deployments', async () => {
        renderPanel(MOCK_AGENT_UNKNOWN);

        expect(await screen.findByText('No deployments for this agent.')).toBeInTheDocument();
      });

      it('Chat button is enabled for running deployments and disabled for others', async () => {
        const user = userEvent.setup();
        renderPanel(MOCK_AGENT_WITH_DEPLOYMENTS);

        // Wait for deployments to load
        await screen.findByText('rag-agent-prod');

        const chatButtons = screen.getAllByRole('button', { name: 'Chat' });
        // rag-agent-prod is running → enabled; sql-agent-dev is stopped → disabled
        expect(chatButtons[0]).not.toBeDisabled();
        expect(chatButtons[1]).toBeDisabled();

        // Clicking Chat on a running deployment switches to Chat Playground
        await user.click(chatButtons[0]);
        expect(screen.getByRole('radio', { name: 'Chat Playground' })).toBeChecked();
      });
    });
  });

  describe('evaluate button', () => {
    it('renders an enabled Evaluate this Agent button when an agent is selected', () => {
      renderPanel(MOCK_AGENT_WITH_DEPLOYMENTS);

      const button = screen.getByRole('button', { name: /Evaluate this Agent/i });
      expect(button).toBeInTheDocument();
      expect(button).not.toBeDisabled();
    });
  });

  describe('defaultTab prop', () => {
    it('opens on the Chat Playground tab when defaultTab is chat-playground', () => {
      render(
        <TestProviders>
          <MemoryRouter>
            <AgentPanel
              agentName={MOCK_AGENT_WITH_DEPLOYMENTS}
              workspace="default"
              open
              defaultTab="chat-playground"
              onOpenChange={vi.fn()}
            />
          </MemoryRouter>
        </TestProviders>
      );

      expect(screen.getByRole('radio', { name: 'Chat Playground' })).toBeChecked();
    });
  });

  describe('chat playground empty state', () => {
    it('shows a Deploy this Agent action when the agent has no healthy deployments', async () => {
      const user = userEvent.setup();
      // react-agent2 has only chat-agent-staging (status=error) → no healthy deployments
      render(
        <TestProviders>
          <MemoryRouter>
            <AgentPanel
              agentName={MOCK_AGENT_WITH_ERROR_DEPLOYMENT}
              workspace="default"
              open
              defaultTab="chat-playground"
              onOpenChange={vi.fn()}
            />
          </MemoryRouter>
        </TestProviders>
      );

      expect(
        await screen.findByText('No healthy deployments available to chat with.')
      ).toBeInTheDocument();

      const deployButton = screen.getByRole('button', { name: /Deploy this Agent/i });
      expect(deployButton).toBeInTheDocument();
      expect(deployButton).not.toBeDisabled();

      await user.click(deployButton);
      // Opening the modal renders its "Deploy Agent" title
      expect(await screen.findByRole('heading', { name: 'Deploy Agent' })).toBeInTheDocument();
    });

    it('shows a deploying spinner when a deployment is mid-transition', async () => {
      server.use(
        http.get(`${PLATFORM_BASE_URL}/apis/agents/v2/workspaces/:workspace/deployments`, () =>
          HttpResponse.json({
            data: [
              {
                name: 'pending-deployment',
                workspace: 'default',
                agent: MOCK_AGENT_WITH_ERROR_DEPLOYMENT,
                status: 'pending',
                endpoint: '',
                port: 0,
                error: '',
              },
            ],
          })
        )
      );

      render(
        <TestProviders>
          <MemoryRouter>
            <AgentPanel
              agentName={MOCK_AGENT_WITH_ERROR_DEPLOYMENT}
              workspace="default"
              open
              defaultTab="chat-playground"
              onOpenChange={vi.fn()}
            />
          </MemoryRouter>
        </TestProviders>
      );

      expect(
        await screen.findByLabelText('Deploying agent', {}, { timeout: 5000 })
      ).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Deploy this Agent/i })).not.toBeInTheDocument();
    });
  });

  describe('onOpenChange', () => {
    it('calls onOpenChange(false) when the panel is closed', async () => {
      const user = userEvent.setup();
      const onOpenChange = vi.fn();

      render(
        <TestProviders>
          <MemoryRouter>
            <AgentPanel
              agentName={MOCK_AGENT_WITH_DEPLOYMENTS}
              workspace="default"
              open
              onOpenChange={onOpenChange}
            />
          </MemoryRouter>
        </TestProviders>
      );

      const closeButton = screen.getByRole('button', { name: /close/i });
      await user.click(closeButton);

      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });
});
