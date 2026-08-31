// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { NMP_BASE_URL } from '@e2e-tests/utils/environment';
import { APIRequestContext } from '@playwright/test';

interface AgentDeployment {
  name?: string;
  agent?: string;
  status?: string;
}

/** Direct API access to the entities an agent run leaves behind, for fixture teardown.
 *
 *  Deleting an agent is rejected while one of its deployments is still active, so a caller
 *  tears the deployments down first and waits for them to disappear. */
export class AgentsAPI {
  constructor(private request: APIRequestContext) {}

  private workspacePath(workspace: string) {
    return `${NMP_BASE_URL}/apis/agents/v2/workspaces/${encodeURIComponent(workspace)}`;
  }

  async listDeploymentsForAgent(workspace: string, agent: string): Promise<AgentDeployment[]> {
    const response = await this.request.get(`${this.workspacePath(workspace)}/deployments`);
    if (!response.ok()) return [];
    const body = (await response.json()) as { data?: AgentDeployment[] };
    return (body.data ?? []).filter((deployment) => deployment.agent === agent);
  }

  async deleteDeployment(workspace: string, name: string) {
    await this.request.delete(
      `${this.workspacePath(workspace)}/deployments/${encodeURIComponent(name)}`
    );
  }

  async deleteAgent(workspace: string, name: string) {
    await this.request.delete(
      `${this.workspacePath(workspace)}/agents/${encodeURIComponent(name)}`
    );
  }

  async deleteFileset(workspace: string, name: string) {
    await this.request.delete(
      `${NMP_BASE_URL}/apis/files/v2/workspaces/${encodeURIComponent(workspace)}/filesets/${encodeURIComponent(name)}`
    );
  }

  /** Deleting an experiment soft-deletes the evaluations whose only membership was that group,
   *  so a run's published results need no separate cleanup call. */
  async deleteExperiment(workspace: string, name: string) {
    await this.request.delete(
      `${NMP_BASE_URL}/apis/intake/v2/workspaces/${encodeURIComponent(workspace)}/experiments/${encodeURIComponent(name)}`
    );
  }

  /** Delete every deployment of an agent and wait for the controller to drop them, so the
   *  agent delete that follows is not rejected as still-deployed. */
  async removeDeployments(workspace: string, agent: string, timeout = 2 * 60 * 1000) {
    for (const deployment of await this.listDeploymentsForAgent(workspace, agent)) {
      if (deployment.name) await this.deleteDeployment(workspace, deployment.name);
    }

    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      if ((await this.listDeploymentsForAgent(workspace, agent)).length === 0) return;
      await new Promise((resolve) => setTimeout(resolve, 5000));
    }
  }
}
