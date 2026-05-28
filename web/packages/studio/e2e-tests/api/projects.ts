// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { NMP_BASE_URL } from '@e2e-tests/utils/environment';
import { ProjectInput, Project, ProjectsPage } from '@nemo/sdk/generated/platform/schema';
import { APIRequestContext } from '@playwright/test';

export class ProjectsAPI {
  constructor(private request: APIRequestContext) {}

  async createProject(workspace: string, data: ProjectInput) {
    const response = await this.request.post(
      `${NMP_BASE_URL}/v2/workspaces/${workspace}/projects`,
      {
        data,
      }
    );
    const responseData = (await response.json()) as Project;
    return responseData;
  }

  async deleteProject(workspace: string, name: string) {
    await this.request.delete(`${NMP_BASE_URL}/v1/projects/${workspace}/${name}`);
  }

  async deleteAllProjectsByWorkspace(workspace: string) {
    const listProjectsResponse = await this.request.get(
      `${NMP_BASE_URL}/v1/projects?filter[workspace]=${workspace}&page_size=100`
    );
    const listProjectsJson = (await listProjectsResponse.json()) as ProjectsPage;
    const projects = listProjectsJson.data;

    projects.forEach(async (project) => {
      await this.deleteProject(project.workspace!, project.name!);
    });
  }
}
