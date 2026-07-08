// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getAgentsListAgentsQueryKey } from '@nemo/sdk/generated/agents/api';
import { getModelsListModelsQueryKey } from '@nemo/sdk/generated/platform/api';
import { markExampleAgentIntroShown } from '@studio/components/sidePanels/AgentPanels/AgentPanel/walkthroughStorage';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { server } from '@studio/mocks/node';
import { AgentsListRoute } from '@studio/routes/agents/AgentsListRoute';
import { getAgentsListRoute } from '@studio/routes/utils';
import { renderRoute, screen, waitFor } from '@studio/tests/util/render';
import { within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

const workspace = workspace1.workspace;
const MODELS_URL = `${PLATFORM_BASE_URL}${getModelsListModelsQueryKey(':workspace')[0]}`;
const CREATE_AGENT_URL = `${PLATFORM_BASE_URL}${getAgentsListAgentsQueryKey(':workspace')[0]}`;

const mockModels = (names: string[]) => {
  server.use(
    http.get(MODELS_URL, () =>
      HttpResponse.json({
        data: names.map((name) => ({ name, workspace })),
        pagination: {
          page: 1,
          page_size: 50,
          current_page_size: names.length,
          total_pages: 1,
          total_results: names.length,
        },
        sort: '-created_at',
        filter: null,
      })
    )
  );
};

const renderList = () =>
  renderRoute(undefined, {
    history: getAgentsListRoute(workspace),
    routes: [
      { path: ROUTES.workspace.agentsList, element: <AgentsListRoute /> },
      { path: ROUTES.workspace.agentDetail, element: <div>Agent detail page</div> },
    ],
  });

const openModal = async (user: ReturnType<typeof userEvent.setup>): Promise<HTMLElement> => {
  await user.click(await screen.findByRole('button', { name: 'Create Example Agent' }));
  const dialog = await screen.findByRole('dialog');
  await within(dialog).findByRole('combobox', { name: 'Model' });
  return dialog;
};

describe('AgentsListRoute', () => {
  beforeEach(() => sessionStorage.clear());

  it('renders the page shell', async () => {
    renderList();
    expect(await screen.findByText('Agents')).toBeInTheDocument();
    expect(
      screen.getByText('View and manage AI agents and their deployments.')
    ).toBeInTheDocument();
  });

  it('opens the modal with the suggested model preselected', async () => {
    const user = userEvent.setup();
    mockModels(['nvidia-nemotron-nano-9b-v2']);
    renderList();

    const dialog = await openModal(user);
    await waitFor(() =>
      expect(within(dialog).getByRole('combobox', { name: 'Model' })).toHaveTextContent(
        'nvidia-nemotron-nano-9b-v2'
      )
    );
  });

  it('creates the example agent with the default suggested model and onboards (navigates)', async () => {
    const user = userEvent.setup();
    mockModels(['meta-llama-3-1-70b-instruct', 'nvidia-nemotron-super-49b']);

    let captured: { name?: string; description?: string; config?: Record<string, unknown> } = {};
    server.use(
      http.post(CREATE_AGENT_URL, async ({ request, params }) => {
        captured = (await request.json()) as typeof captured;
        return HttpResponse.json({ ...captured, workspace: params['workspace'] });
      })
    );

    renderList();
    const dialog = await openModal(user);
    await waitFor(() =>
      expect(within(dialog).getByRole('combobox', { name: 'Model' })).toHaveTextContent(
        'nvidia-nemotron-super-49b'
      )
    );
    await user.click(within(dialog).getByRole('button', { name: 'Create' }));

    expect(await screen.findByText('Agent detail page')).toBeInTheDocument();

    expect(captured.name).toMatch(/^calculator-demo-agent-[a-z0-9]{6}$/);
    expect(captured.description).toBeTruthy();
    const config = captured.config as {
      workflow: { _type: string; tool_names: string[]; use_native_tool_calling: boolean };
      function_groups: Record<string, { _type: string }>;
      functions: Record<string, { _type: string }>;
      llms: { llm: { model_name: string } };
    };
    expect(config.workflow._type).toBe('react_agent');
    expect(config.workflow.tool_names).toEqual(['calculator', 'current_datetime']);
    expect(config.workflow.use_native_tool_calling).toBe(true);
    expect(config.function_groups.calculator._type).toBe('calculator');
    expect(config.functions.current_datetime._type).toBe('current_datetime');
    expect(config.llms.llm.model_name).toBe('nvidia-nemotron-super-49b');
  });

  it('lets the user pick a different model', async () => {
    const user = userEvent.setup();
    mockModels(['nvidia-nemotron-super-49b', 'meta-llama-3-1-70b-instruct']);

    let modelName: string | undefined;
    server.use(
      http.post(CREATE_AGENT_URL, async ({ request, params }) => {
        const body = (await request.json()) as {
          config: { llms: { llm: { model_name: string } } };
        };
        modelName = body.config.llms.llm.model_name;
        return HttpResponse.json({
          name: 'calculator-demo-agent-abc123',
          workspace: params['workspace'],
        });
      })
    );

    renderList();
    const dialog = await openModal(user);
    await waitFor(() =>
      expect(within(dialog).getByRole('combobox', { name: 'Model' })).toHaveTextContent(
        'nvidia-nemotron-super-49b'
      )
    );

    await user.click(within(dialog).getByRole('combobox', { name: 'Model' }));
    await user.click(await screen.findByRole('option', { name: 'meta-llama-3-1-70b-instruct' }));
    await user.click(within(dialog).getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(modelName).toBe('meta-llama-3-1-70b-instruct'));
  });

  it('creates the email phishing example when that example is selected', async () => {
    const user = userEvent.setup();
    mockModels(['nvidia-nemotron-super-49b']);

    let captured: { name?: string; description?: string; config?: Record<string, unknown> } = {};
    server.use(
      http.post(CREATE_AGENT_URL, async ({ request, params }) => {
        captured = (await request.json()) as typeof captured;
        return HttpResponse.json({ ...captured, workspace: params['workspace'] });
      })
    );

    renderList();
    const dialog = await openModal(user);
    await waitFor(() =>
      expect(within(dialog).getByRole('combobox', { name: 'Model' })).toHaveTextContent(
        'nvidia-nemotron-super-49b'
      )
    );

    await user.click(within(dialog).getByRole('combobox', { name: 'Example' }));
    await user.click(await screen.findByRole('option', { name: 'email_phishing_analyzer' }));
    await user.click(within(dialog).getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(captured.name).toMatch(/^email-phishing-demo-agent-[a-z0-9]{6}$/));
    const config = captured.config as {
      workflow: { tool_names: string[] };
      functions: Record<string, { _type: string }>;
      llms: { llm: { model_name: string } };
    };
    expect(config.workflow.tool_names).toEqual(['email_phishing_analyzer']);
    expect(config.functions.email_phishing_analyzer._type).toBe('email_phishing_analyzer');
    expect(config.llms.llm.model_name).toBe('nvidia-nemotron-super-49b');
  });

  it('excludes non-chat models from the picker', async () => {
    const user = userEvent.setup();
    mockModels(['nvidia-nv-embedqa-e5-v5', 'nvidia-nemotron-nano-9b-v2']);
    renderList();

    const dialog = await openModal(user);
    await waitFor(() =>
      expect(within(dialog).getByRole('combobox', { name: 'Model' })).toHaveTextContent(
        'nvidia-nemotron-nano-9b-v2'
      )
    );
    await user.click(within(dialog).getByRole('combobox', { name: 'Model' }));

    expect(
      await screen.findByRole('option', { name: 'nvidia-nemotron-nano-9b-v2' })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('option', { name: 'nvidia-nv-embedqa-e5-v5' })
    ).not.toBeInTheDocument();
  });

  it('refetches the agents list after creating so the new agent appears immediately', async () => {
    const user = userEvent.setup();
    mockModels(['nvidia-nemotron-nano-9b-v2']);
    // Returning user → stays on the list, so the table query is still mounted.
    markExampleAgentIntroShown();

    let agentListFetches = 0;
    server.use(
      http.get(CREATE_AGENT_URL, () => {
        agentListFetches += 1;
        return HttpResponse.json({
          data: [],
          pagination: {
            page: 1,
            page_size: 50,
            current_page_size: 0,
            total_pages: 1,
            total_results: 0,
          },
          sort: '-created_at',
          filter: null,
        });
      }),
      http.post(CREATE_AGENT_URL, async ({ request, params }) => {
        const body = (await request.json()) as { name?: string };
        return HttpResponse.json({ ...body, workspace: params['workspace'] });
      })
    );

    renderList();
    await waitFor(() => expect(agentListFetches).toBeGreaterThan(0));
    const before = agentListFetches;

    const dialog = await openModal(user);
    await waitFor(() =>
      expect(within(dialog).getByRole('combobox', { name: 'Model' })).toHaveTextContent(
        'nvidia-nemotron-nano-9b-v2'
      )
    );
    await user.click(within(dialog).getByRole('button', { name: 'Create' }));

    // Create invalidates the list, triggering an immediate refetch (not the 15s poll).
    await waitFor(() => expect(agentListFetches).toBeGreaterThan(before));
  });

  it('does not onboard for a later example agent in the same session', async () => {
    const user = userEvent.setup();
    mockModels(['nvidia-nemotron-nano-9b-v2']);
    markExampleAgentIntroShown();

    let created = false;
    server.use(
      http.post(CREATE_AGENT_URL, async ({ request, params }) => {
        created = true;
        const body = (await request.json()) as { name?: string };
        return HttpResponse.json({ ...body, workspace: params['workspace'] });
      })
    );

    renderList();
    const dialog = await openModal(user);
    await waitFor(() =>
      expect(within(dialog).getByRole('combobox', { name: 'Model' })).toHaveTextContent(
        'nvidia-nemotron-nano-9b-v2'
      )
    );
    await user.click(within(dialog).getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(created).toBe(true));
    expect(screen.queryByText('Agent detail page')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create Example Agent' })).toBeInTheDocument();
  });

  it('does not onboard when an example agent already exists in the workspace', async () => {
    const user = userEvent.setup();
    mockModels(['nvidia-nemotron-nano-9b-v2']);
    server.use(
      http.get(CREATE_AGENT_URL, () =>
        HttpResponse.json({
          data: [{ name: 'calculator-demo-agent-abc123', workspace }],
          pagination: {
            page: 1,
            page_size: 50,
            current_page_size: 1,
            total_pages: 1,
            total_results: 1,
          },
          sort: '-created_at',
          filter: null,
        })
      )
    );

    let created = false;
    server.use(
      http.post(CREATE_AGENT_URL, async ({ request, params }) => {
        created = true;
        const body = (await request.json()) as { name?: string };
        return HttpResponse.json({ ...body, workspace: params['workspace'] });
      })
    );

    renderList();
    await screen.findByText('calculator-demo-agent-abc123');
    const dialog = await openModal(user);
    await waitFor(() =>
      expect(within(dialog).getByRole('combobox', { name: 'Model' })).toHaveTextContent(
        'nvidia-nemotron-nano-9b-v2'
      )
    );
    await user.click(within(dialog).getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(created).toBe(true));
    expect(screen.queryByText('Agent detail page')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create Example Agent' })).toBeInTheDocument();
  });

  it('does not create when the workspace has no models', async () => {
    const user = userEvent.setup();
    mockModels([]);

    let createCalled = false;
    server.use(
      http.post(CREATE_AGENT_URL, () => {
        createCalled = true;
        return HttpResponse.json({ name: 'unexpected', workspace });
      })
    );

    renderList();
    const dialog = await openModal(user);
    await user.click(within(dialog).getByRole('button', { name: 'Create' }));

    await waitFor(() =>
      expect(within(dialog).getByRole('combobox', { name: 'Model' })).toBeInTheDocument()
    );
    expect(createCalled).toBe(false);
  });
});
