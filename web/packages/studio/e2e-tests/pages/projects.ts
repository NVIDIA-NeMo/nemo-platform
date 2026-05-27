// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { expectToastIsVisible, waitForLongOperation } from '@e2e-tests/utils/pageUtils';
import { getRowByName } from '@e2e-tests/utils/tables';
import { expect, type Page } from '@playwright/test';

const PROJECTS_PAGE_URL = `projects?sort_by=created_at&order=desc`;

export class ProjectsPage {
  constructor(public readonly page: Page) {}

  private async openQuickActionsMenu(projectName: string, actionName: string) {
    const projectRow = await getRowByName(this.page, projectName);

    await expect(projectRow).toBeVisible();
    await projectRow.getByTestId('quick-actions-menu-trigger').click();
    await this.page.getByRole('menuitem', { name: actionName }).click();
  }

  async goto() {
    await this.page.goto(PROJECTS_PAGE_URL);
  }

  async createProject(displayName: string, description: string) {
    // Click the button that triggers the modal to open
    await this.page.getByRole('button', { name: 'New Project' }).click();
    // Fill out form for new project
    await this.page.getByRole('textbox', { name: 'Project Name' }).fill(displayName);
    await this.page.getByRole('textbox', { name: 'Description' }).fill(description);
    // Submit button
    await this.page.getByRole('button', { name: 'Create Project' }).click();
  }

  async updateProject(existingName: string, description: string) {
    await this.openQuickActionsMenu(existingName, 'Edit');
    await this.page.getByTestId('project-update-modal').waitFor({ state: 'visible' });
    await this.page.getByRole('textbox', { name: 'Description' }).fill(`${description} Updated`);
    await this.page.getByRole('button', { name: 'Update Project' }).click();
    await waitForLongOperation(this.page);

    await expectToastIsVisible(this.page, 'Successfully updated project!');
  }

  async deleteProject(displayName: string) {
    await this.openQuickActionsMenu(displayName, 'Delete');
    // Fill out form
    await this.page.getByRole('button', { name: 'Delete' }).click();
    await waitForLongOperation(this.page);
    await expectToastIsVisible(this.page, 'Successfully deleted!');
  }

  async waitForPageLoad() {
    await waitForLongOperation(this.page);
  }
}
