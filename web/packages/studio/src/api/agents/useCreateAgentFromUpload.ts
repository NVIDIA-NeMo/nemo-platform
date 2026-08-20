// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { agentsCreateAgent, agentsDeleteAgent } from '@nemo/sdk/generated/agents/api';
import type { Agent } from '@nemo/sdk/generated/agents/schema/Agent';
import {
  filesCreateFileset,
  filesDeleteFileset,
  filesRetrieveFileset,
  filesUploadFile,
} from '@nemo/sdk/generated/platform/api';
import {
  AGENT_CONFIG_FILENAME,
  agentSpecFilesetName,
  FABRIC_CONFIG_FORMAT,
  parseAgentConfig,
} from '@studio/routes/agents/AgentsListRoute/UploadAgentModal/const';
import type { UploadAgentEntry } from '@studio/routes/agents/AgentsListRoute/UploadAgentModal/type';
import { UseMutationOptions, useMutation } from '@tanstack/react-query';

export interface CreateAgentFromUploadParams {
  workspace: string;
  name: string;
  entries: UploadAgentEntry[];
}

export class AgentSpecFilesetConflictError extends Error {
  constructor(public readonly filesetName: string) {
    super(
      `A fileset named "${filesetName}" already exists. It holds the spec for an agent of this name — possibly one that was deleted, since deleting an agent leaves its fileset behind. Delete it with \`nemo files filesets delete ${filesetName}\`, or choose a different name.`
    );
  }
}

/**
 * Create a Fabric agent from a picked directory.
 *
 * Two phases, because the platform has no endpoint that takes config and files
 * together: the agent entity is created first so the name is reserved (and a
 * duplicate returns 409), then the directory is uploaded into the conventional
 * `{agent}-spec` fileset that deployments read.
 *
 * Both are rolled back on failure. Deleting the fileset is safe here only
 * because an existing one is refused up front — so anything this flow uploaded
 * into it, this flow created.
 */
export const createAgentFromUpload = async ({
  workspace,
  name,
  entries,
}: CreateAgentFromUploadParams): Promise<Agent> => {
  const filesetName = agentSpecFilesetName(name);

  await assertFilesetAvailable(workspace, filesetName);

  const configEntry = entries.find((entry) => entry.path === AGENT_CONFIG_FILENAME);
  if (!configEntry) throw new Error(`No ${AGENT_CONFIG_FILENAME} in the selected directory.`);
  const config = parseAgentConfig(await configEntry.file.text());

  const agent = await agentsCreateAgent(workspace, {
    name,
    description: typeof config.description === 'string' ? config.description : '',
    config,
    config_format: FABRIC_CONFIG_FORMAT,
  });

  try {
    await filesCreateFileset(workspace, {
      name: filesetName,
      description: `Agent spec for ${name}`,
    });
    await uploadEntries(workspace, filesetName, entries);
  } catch (error) {
    await rollback(workspace, name, filesetName);
    throw error;
  }

  return agent;
};

const assertFilesetAvailable = async (workspace: string, filesetName: string): Promise<void> => {
  try {
    await filesRetrieveFileset(workspace, filesetName);
  } catch {
    return;
  }
  throw new AgentSpecFilesetConflictError(filesetName);
};

/**
 * Upload sequentially. The files service takes one file per request, and a
 * directory is bounded at 500 files, so ordered failure beats saturating the
 * browser's connection pool for a marginal speedup.
 */
const uploadEntries = async (
  workspace: string,
  filesetName: string,
  entries: UploadAgentEntry[]
): Promise<void> => {
  for (const entry of entries) {
    const blob = new Blob([await entry.file.arrayBuffer()], { type: 'application/octet-stream' });
    await filesUploadFile(workspace, filesetName, entry.path, blob);
  }
};

const rollback = async (
  workspace: string,
  agentName: string,
  filesetName: string
): Promise<void> => {
  await Promise.allSettled([
    agentsDeleteAgent(workspace, agentName),
    filesDeleteFileset(workspace, filesetName),
  ]);
};

export type UseCreateAgentFromUploadOptions = Omit<
  UseMutationOptions<Agent, Error, CreateAgentFromUploadParams>,
  'mutationFn'
>;

export const useCreateAgentFromUpload = (options?: UseCreateAgentFromUploadOptions) =>
  useMutation({ ...options, mutationFn: createAgentFromUpload });
