// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { NMP_BASE_URL } from '@e2e-tests/utils/environment';
import { Workspace, WorkspaceInput, WorkspacesPage } from '@nemo/sdk/generated/platform/schema';
import { APIRequestContext } from '@playwright/test';

export class WorkspacesAPI {
  constructor(private request: APIRequestContext) {}

  async createWorkspace(data: WorkspaceInput) {
    const response = await this.request.post(`${NMP_BASE_URL}/apis/entities/v2/workspaces`, {
      data,
    });
    return (await response.json()) as Workspace;
  }

  async deleteWorkspace(name: string) {
    await this.request.delete(`${NMP_BASE_URL}/apis/entities/v2/workspaces/${name}`);
  }

  async listWorkspaces() {
    const response = await this.request.get(
      `${NMP_BASE_URL}/apis/entities/v2/workspaces?page_size=100`
    );
    return (await response.json()) as WorkspacesPage;
  }

  async deleteAllWorkspacesByPrefix(prefix: string) {
    const list = await this.listWorkspaces();
    for (const workspace of list.data) {
      if (workspace.name.startsWith(prefix)) {
        await this.deleteWorkspace(workspace.name);
      }
    }
  }
}
