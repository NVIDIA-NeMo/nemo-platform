// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { agentsCreateAgent, agentsDeleteAgent } from '@nemo/sdk/generated/agents/api';
import {
  filesCreateFileset,
  filesDeleteFileset,
  filesRetrieveFileset,
  filesUploadFile,
} from '@nemo/sdk/generated/platform/api';
import {
  AgentSpecFilesetConflictError,
  createAgentFromUpload,
} from '@studio/api/agents/useCreateAgentFromUpload';
import type { UploadAgentEntry } from '@studio/routes/agents/AgentsListRoute/UploadAgentModal/type';

vi.mock('@nemo/sdk/generated/agents/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@nemo/sdk/generated/agents/api')>()),
  agentsCreateAgent: vi.fn(),
  agentsDeleteAgent: vi.fn(),
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

beforeEach(() => {
  vi.mocked(filesRetrieveFileset).mockRejectedValue(new Error('404'));
  vi.mocked(filesCreateFileset).mockResolvedValue({ name: 'calc-spec' } as never);
  vi.mocked(filesUploadFile).mockResolvedValue({ path: 'agent.yaml' } as never);
  vi.mocked(filesDeleteFileset).mockResolvedValue(undefined as never);
  vi.mocked(agentsCreateAgent).mockResolvedValue({ name: 'calc' } as never);
  vi.mocked(agentsDeleteAgent).mockResolvedValue(undefined as never);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('createAgentFromUpload', () => {
  it('creates the agent, then uploads every file into the {agent}-spec fileset', async () => {
    await createAgentFromUpload(params());

    expect(agentsCreateAgent).toHaveBeenCalledWith('ws', {
      name: 'calc',
      description: 'Adds numbers',
      config: expect.objectContaining({ config_format: 'nemo-agents-spec-v1' }),
      config_format: 'nemo-agents-spec-v1',
    });
    expect(filesCreateFileset).toHaveBeenCalledWith('ws', expect.objectContaining({ name: 'calc-spec' }));
    expect(vi.mocked(filesUploadFile).mock.calls.map((call) => [call[1], call[2]])).toEqual([
      ['calc-spec', 'agent.yaml'],
      ['calc-spec', 'mcps/calculator.py'],
    ]);
  });

  it('refuses to touch an existing spec fileset', async () => {
    vi.mocked(filesRetrieveFileset).mockResolvedValue({ name: 'calc-spec' } as never);

    await expect(createAgentFromUpload(params())).rejects.toThrow(AgentSpecFilesetConflictError);
    expect(agentsCreateAgent).not.toHaveBeenCalled();
    expect(filesCreateFileset).not.toHaveBeenCalled();
  });

  it('deletes the agent and the fileset when an upload fails', async () => {
    vi.mocked(filesUploadFile)
      .mockResolvedValueOnce({ path: 'agent.yaml' } as never)
      .mockRejectedValueOnce(new Error('network down'));

    await expect(createAgentFromUpload(params())).rejects.toThrow('network down');
    expect(agentsDeleteAgent).toHaveBeenCalledWith('ws', 'calc');
    expect(filesDeleteFileset).toHaveBeenCalledWith('ws', 'calc-spec');
  });

  it('rejects a non-Fabric config before creating anything', async () => {
    const natEntries = [entryFor('agent.yaml', 'config_format: nat-workflow-v1\n')];

    await expect(
      createAgentFromUpload({ workspace: 'ws', name: 'calc', entries: natEntries })
    ).rejects.toThrow(/config_format/);
    expect(agentsCreateAgent).not.toHaveBeenCalled();
  });
});
