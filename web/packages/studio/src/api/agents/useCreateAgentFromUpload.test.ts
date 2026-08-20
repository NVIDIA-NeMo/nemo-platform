// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { agentsCreateAgent, agentsGetAgent } from '@nemo/sdk/generated/agents/api';
import {
  filesCreateFileset,
  filesDeleteFileset,
  filesRetrieveFileset,
  filesUploadFile,
} from '@nemo/sdk/generated/platform/api';
import {
  AgentSpecFilesetConflictError,
  AgentSpecFilesetOrphanError,
  createAgentFromUpload,
} from '@studio/api/agents/useCreateAgentFromUpload';
import type { UploadAgentEntry } from '@studio/routes/agents/AgentsListRoute/UploadAgentModal/type';

vi.mock('@nemo/sdk/generated/agents/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@nemo/sdk/generated/agents/api')>()),
  agentsCreateAgent: vi.fn(),
  agentsGetAgent: vi.fn(),
}));

vi.mock('@nemo/sdk/generated/platform/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@nemo/sdk/generated/platform/api')>()),
  filesRetrieveFileset: vi.fn(),
  filesCreateFileset: vi.fn(),
  filesUploadFile: vi.fn(),
  filesDeleteFileset: vi.fn(),
}));

const FABRIC_YAML = 'config_format: nemo-agents-spec-v1\nname: calc\ndescription: Adds numbers\n';

const entryFor = (path: string, contents: string): UploadAgentEntry => ({
  path,
  file: new File([contents], path.split('/').pop() ?? path),
});

const entries = (): UploadAgentEntry[] => [
  entryFor('agent.yaml', FABRIC_YAML),
  entryFor('mcps/calculator.py', 'print(1)\n'),
];

const params = () => ({ workspace: 'ws', name: 'calc', entries: entries() });

const filesetMissing = () => vi.mocked(filesRetrieveFileset).mockRejectedValue(new Error('404'));
const filesetExists = () =>
  vi.mocked(filesRetrieveFileset).mockResolvedValue({ name: 'calc-spec' } as never);
const agentMissing = () => vi.mocked(agentsGetAgent).mockRejectedValue(new Error('404'));
const agentExists = () => vi.mocked(agentsGetAgent).mockResolvedValue({ name: 'calc' } as never);

beforeEach(() => {
  filesetMissing();
  agentMissing();
  vi.mocked(filesCreateFileset).mockResolvedValue({ name: 'calc-spec' } as never);
  vi.mocked(filesUploadFile).mockResolvedValue({ path: 'agent.yaml' } as never);
  vi.mocked(filesDeleteFileset).mockResolvedValue(undefined as never);
  vi.mocked(agentsCreateAgent).mockResolvedValue({ name: 'calc' } as never);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('createAgentFromUpload', () => {
  it('uploads every file before creating the agent', async () => {
    const order: string[] = [];
    vi.mocked(filesUploadFile).mockImplementation(async (_ws, _fs, path) => {
      order.push(`upload:${path}`);
      return { path } as never;
    });
    vi.mocked(agentsCreateAgent).mockImplementation(async () => {
      order.push('createAgent');
      return { name: 'calc' } as never;
    });

    await createAgentFromUpload(params());

    expect(order).toEqual(['upload:agent.yaml', 'upload:mcps/calculator.py', 'createAgent']);
    expect(agentsCreateAgent).toHaveBeenCalledWith('ws', {
      name: 'calc',
      description: 'Adds numbers',
      config: expect.objectContaining({ config_format: 'nemo-agents-spec-v1' }),
      config_format: 'nemo-agents-spec-v1',
    });
  });

  it('refuses a fileset that an existing agent owns', async () => {
    filesetExists();
    agentExists();

    await expect(createAgentFromUpload(params())).rejects.toThrow(AgentSpecFilesetConflictError);
    expect(filesCreateFileset).not.toHaveBeenCalled();
    expect(filesDeleteFileset).not.toHaveBeenCalled();
  });

  it('asks before replacing a fileset that no agent owns', async () => {
    filesetExists();

    await expect(createAgentFromUpload(params())).rejects.toThrow(AgentSpecFilesetOrphanError);
    expect(filesDeleteFileset).not.toHaveBeenCalled();
    expect(agentsCreateAgent).not.toHaveBeenCalled();
  });

  it('replaces an orphaned fileset once confirmed', async () => {
    filesetExists();

    await createAgentFromUpload({ ...params(), replaceOrphanedFileset: true });

    expect(filesDeleteFileset).toHaveBeenCalledWith('ws', 'calc-spec');
    expect(filesCreateFileset).toHaveBeenCalledWith(
      'ws',
      expect.objectContaining({ name: 'calc-spec' })
    );
    expect(agentsCreateAgent).toHaveBeenCalled();
  });

  it('does not replace an owned fileset even when confirmed', async () => {
    filesetExists();
    agentExists();

    await expect(
      createAgentFromUpload({ ...params(), replaceOrphanedFileset: true })
    ).rejects.toThrow(AgentSpecFilesetConflictError);
    expect(filesDeleteFileset).not.toHaveBeenCalled();
  });

  it('deletes the fileset when an upload fails', async () => {
    vi.mocked(filesUploadFile)
      .mockResolvedValueOnce({ path: 'agent.yaml' } as never)
      .mockRejectedValueOnce(new Error('network down'));

    await expect(createAgentFromUpload(params())).rejects.toThrow('network down');
    expect(filesDeleteFileset).toHaveBeenCalledWith('ws', 'calc-spec');
  });

  it('deletes the fileset when creating the agent fails', async () => {
    vi.mocked(agentsCreateAgent).mockRejectedValue(new Error('409 conflict'));

    await expect(createAgentFromUpload(params())).rejects.toThrow('409 conflict');
    expect(filesDeleteFileset).toHaveBeenCalledWith('ws', 'calc-spec');
  });

  it('rejects a non-Fabric config before touching anything', async () => {
    const natEntries = [entryFor('agent.yaml', 'config_format: nat-workflow-v1\n')];

    await expect(
      createAgentFromUpload({ workspace: 'ws', name: 'calc', entries: natEntries })
    ).rejects.toThrow(/config_format/);
    expect(filesRetrieveFileset).not.toHaveBeenCalled();
    expect(filesCreateFileset).not.toHaveBeenCalled();
    expect(agentsCreateAgent).not.toHaveBeenCalled();
  });
});
