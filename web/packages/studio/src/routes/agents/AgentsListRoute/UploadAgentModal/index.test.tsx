// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { server } from '@studio/mocks/node';
import { UploadAgentModal } from '@studio/routes/agents/AgentsListRoute/UploadAgentModal';
import { getAgentsListRoute } from '@studio/routes/utils';
import { renderRoute, screen, waitFor } from '@studio/tests/util/render';
import { fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

const workspace = workspace1.workspace;
const FILESETS_URL = `${PLATFORM_BASE_URL}/apis/files/v2/workspaces/:workspace/filesets`;
const FILESET_URL = `${FILESETS_URL}/:name`;
const UPLOAD_URL = `${FILESET_URL}/-/*`;
const AGENTS_URL = `${PLATFORM_BASE_URL}/apis/agents/v2/workspaces/:workspace/agents`;
const AGENT_URL = `${AGENTS_URL}/:name`;

const FABRIC_YAML = `config_format: nemo-agents-spec-v1
name: calc
description: Adds numbers
`;

const makeFile = (relativePath: string, contents: string): File => {
  const file = new File([contents], relativePath.split('/').pop() ?? relativePath, {
    type: 'text/plain',
  });
  Object.defineProperty(file, 'webkitRelativePath', { value: relativePath });
  return file;
};

const DEFAULT_FILES = [
  makeFile('calc-agent/agent.yaml', FABRIC_YAML),
  makeFile('calc-agent/mcps/calculator.py', 'print(1)\n'),
];

interface Scenario {
  filesetExists?: boolean;
  agentExists?: boolean;
}

const mockPlatform = ({ filesetExists = false, agentExists = false }: Scenario = {}) => {
  const uploaded: string[] = [];
  const created: { name?: string }[] = [];

  server.use(
    http.get(FILESET_URL, ({ params }) =>
      filesetExists
        ? HttpResponse.json({ name: params['name'], workspace })
        : HttpResponse.json({ detail: 'not found' }, { status: 404 })
    ),
    http.get(AGENT_URL, ({ params }) =>
      agentExists
        ? HttpResponse.json({ name: params['name'], workspace })
        : HttpResponse.json({ detail: 'not found' }, { status: 404 })
    ),
    http.delete(FILESET_URL, () => HttpResponse.json({ name: 'deleted' })),
    http.post(FILESETS_URL, async ({ request }) =>
      HttpResponse.json(await request.json())
    ),
    http.put(UPLOAD_URL, ({ request }) => {
      uploaded.push(decodeURIComponent(new URL(request.url).pathname.split('/-/')[1] ?? ''));
      return HttpResponse.json({ path: 'ok' });
    }),
    http.post(AGENTS_URL, async ({ request }) => {
      const body = (await request.json()) as { name?: string };
      created.push(body);
      return HttpResponse.json({ ...body, workspace }, { status: 201 });
    })
  );

  return { uploaded, created };
};

const renderModal = () =>
  renderRoute(undefined, {
    history: getAgentsListRoute(workspace),
    routes: [
      {
        path: ROUTES.workspace.agentsList,
        element: <UploadAgentModal open onClose={vi.fn()} workspace={workspace} />,
      },
      { path: ROUTES.workspace.agentDetail, element: <div>Agent detail page</div> },
    ],
  });

const pickDirectory = (dialog: HTMLElement, files: File[] = DEFAULT_FILES) => {
  fireEvent.change(within(dialog).getByTestId('agent-directory-input'), { target: { files } });
};

const submit = async (dialog: HTMLElement, user: ReturnType<typeof userEvent.setup>) => {
  await user.click(within(dialog).getByRole('button', { name: /^(Create|Replace and create)$/ }));
};

describe('UploadAgentModal', () => {
  it('uploads the picked directory, then creates the agent', async () => {
    const user = userEvent.setup();
    const { uploaded, created } = mockPlatform();

    renderModal();
    const dialog = await screen.findByRole('dialog');
    pickDirectory(dialog);
    await waitFor(() => expect(within(dialog).getByDisplayValue('calc')).toBeInTheDocument());

    await submit(dialog, user);

    await waitFor(() => expect(created).toHaveLength(1));
    expect(uploaded).toEqual(['agent.yaml', 'mcps/calculator.py']);
    expect(created[0]?.name).toBe('calc');
  });

  it('shows why an owned name is refused instead of a generic failure', async () => {
    const user = userEvent.setup();
    const { created } = mockPlatform({ filesetExists: true, agentExists: true });

    renderModal();
    const dialog = await screen.findByRole('dialog');
    pickDirectory(dialog);
    await waitFor(() => expect(within(dialog).getByDisplayValue('calc')).toBeInTheDocument());

    await submit(dialog, user);

    expect(await within(dialog).findByText(/already owns the fileset/)).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Create' })).toBeInTheDocument();
    expect(created).toHaveLength(0);
  });

  it('offers to replace an orphaned fileset, and replaces it on the next submit', async () => {
    const user = userEvent.setup();
    const { created } = mockPlatform({ filesetExists: true });

    renderModal();
    const dialog = await screen.findByRole('dialog');
    pickDirectory(dialog);
    await waitFor(() => expect(within(dialog).getByDisplayValue('calc')).toBeInTheDocument());

    await submit(dialog, user);
    expect(await within(dialog).findByText(/no agent owns it/)).toBeInTheDocument();

    const replace = await within(dialog).findByRole('button', { name: 'Replace and create' });
    await user.click(replace);

    await waitFor(() => expect(created).toHaveLength(1));
  });

  it('rejects a directory with no agent.yaml at the top level', async () => {
    mockPlatform();

    renderModal();
    const dialog = await screen.findByRole('dialog');
    pickDirectory(dialog, [makeFile('calc-agent/mcps/calculator.py', 'print(1)\n')]);

    expect(await within(dialog).findByText(/No agent\.yaml/)).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Create' })).toBeDisabled();
  });

  it('rejects a directory holding a file that is not text', async () => {
    mockPlatform();

    renderModal();
    const dialog = await screen.findByRole('dialog');
    pickDirectory(dialog, [
      makeFile('calc-agent/agent.yaml', FABRIC_YAML),
      new File([new Uint8Array([0xff, 0xfe, 0x00])], 'logo.bin'),
    ]);

    expect(await within(dialog).findByText(/is not a text file/)).toBeInTheDocument();
  });
});

describe('UploadAgentModal tabs', () => {
  it('offers the designed coding-agent prompt', async () => {
    const user = userEvent.setup();
    mockPlatform();

    renderModal();
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('tab', { name: 'Coding agent prompt' }));

    expect(
      await within(dialog).findByText(/Integrate my agent with NeMo Platform/)
    ).toBeInTheDocument();
  });

  it('shows a CLI command carrying the entered name', async () => {
    const user = userEvent.setup();
    mockPlatform();

    renderModal();
    const dialog = await screen.findByRole('dialog');
    pickDirectory(dialog);
    await waitFor(() => expect(within(dialog).getByDisplayValue('calc')).toBeInTheDocument());

    await user.click(within(dialog).getByRole('tab', { name: 'CLI command' }));

    await waitFor(() => expect(dialog).toHaveTextContent('nemo agents create'));
    expect(dialog).toHaveTextContent('--name calc');
  });
});
