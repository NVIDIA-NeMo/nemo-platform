// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getAgentsListAgentsQueryKey } from '@nemo/sdk/generated/agents/api';
import { getModelsListModelsQueryKey } from '@nemo/sdk/generated/platform/api';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { server } from '@studio/mocks/node';
import { AgentsListRoute } from '@studio/routes/agents/AgentsListRoute';
import { getAgentsListRoute } from '@studio/routes/utils';
import { renderRoute, screen, waitFor } from '@studio/tests/util/render';
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

// Click the button as soon as it's in the DOM; the handler queues the create if models
// are still loading and executes once they settle.
const clickCreateOnceReady = async (user: ReturnType<typeof userEvent.setup>) => {
  const button = await screen.findByRole('button', { name: 'Create Example Agent' });
  await user.click(button);
};

describe('AgentsListRoute', () => {
  it('renders the page shell', async () => {
    renderList();
    expect(await screen.findByText('Agents')).toBeInTheDocument();
    expect(
      screen.getByText('View and manage AI agents and their deployments.')
    ).toBeInTheDocument();
  });

  it('creates the calculator example agent in one click and navigates to it', async () => {
    const user = userEvent.setup();
    mockModels(['nvidia-nemotron-nano-9b-v2']);

    let captured: { name?: string; description?: string; config?: Record<string, unknown> } = {};
    server.use(
      http.post(CREATE_AGENT_URL, async ({ request, params }) => {
        captured = (await request.json()) as typeof captured;
        return HttpResponse.json({ ...captured, workspace: params['workspace'] });
      })
    );

    renderList();

    await clickCreateOnceReady(user);

    // Navigated to the new agent's detail page on success.
    expect(await screen.findByText('Agent detail page')).toBeInTheDocument();

    // Unique, registry-safe name so repeated clicks don't collide.
    expect(captured.name).toMatch(/^calculator-demo-agent-[a-z0-9]{6}$/);
    expect(captured.description).toBeTruthy();

    // Calculator NAT config: ReAct workflow + calculator function group + datetime tool.
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
    // A concrete workspace model is chosen (service does not resolve ${NEMO_DEFAULT_MODEL}).
    expect(config.llms.llm.model_name).toBe('nvidia-nemotron-nano-9b-v2');
  });

  it('prefers a suggested Nemotron model over a non-suggested one', async () => {
    const user = userEvent.setup();
    // "All Models" order puts the non-Nemotron model first; selection must still
    // prefer the suggested Nemotron model rather than blindly taking the first.
    mockModels(['meta-llama-3-1-70b-instruct', 'nvidia-nemotron-super-49b']);

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
    await clickCreateOnceReady(user);

    await waitFor(() => expect(modelName).toBe('nvidia-nemotron-super-49b'));
  });

  it('does not auto-select a non-LLM model; surfaces an error instead', async () => {
    const user = userEvent.setup();
    // Workspace has only an embedding model — not a usable agent LLM.
    mockModels(['nvidia-nv-embedqa-e5-v5']);

    let createCalled = false;
    server.use(
      http.post(CREATE_AGENT_URL, () => {
        createCalled = true;
        return HttpResponse.json({ name: 'unexpected', workspace });
      })
    );

    renderList();
    await clickCreateOnceReady(user);

    expect(await screen.findByText(/No usable chat model in this workspace/i)).toBeInTheDocument();
    expect(createCalled).toBe(false);
  });

  it('does not create an agent and surfaces an error when the workspace has no models', async () => {
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
    await clickCreateOnceReady(user);

    expect(await screen.findByText(/No usable chat model in this workspace/i)).toBeInTheDocument();
    expect(createCalled).toBe(false);
  });
});
