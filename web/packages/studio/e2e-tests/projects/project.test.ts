// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ProjectsAPI } from '@e2e-tests/api/projects';
import { ProjectsPage } from '@e2e-tests/pages/projects';
import {
  CURRENT_YYYY_MM_DD,
  LONG_OPERATION_TIMEOUT,
  buildTestNamespace,
  generateTestResourceName,
} from '@e2e-tests/utils/constants';
import { INTAKE_ENABLED } from '@e2e-tests/utils/environment';
import { TestProjectFixture, testProjectFixture } from '@e2e-tests/utils/fixtures';
import { disableAuthForTest } from '@e2e-tests/utils/pageUtils';
import { stripBasePath } from '@e2e-tests/utils/routes';
import { expect, test as baseTest } from '@playwright/test';
import { ROUTES } from '@studio/constants/routes';
import { matchPath } from 'react-router';

// Route the user should be redirected to creating a project
const PROJECT_LANDING_PAGE = ROUTES.workspace.dashboard;
// Namespace for test projects created by this test suite's fixtures
const PROJECT_NAMESPACE = buildTestNamespace('project');

interface TestFixtures {
  projectsPage: ProjectsPage;
  projectsApi: ProjectsAPI;
  testProject: TestProjectFixture;
}

const test = baseTest.extend<TestFixtures>({
  projectsPage: async ({ page }, runFixture) => {
    await runFixture(new ProjectsPage(page));
  },
  projectsApi: async ({ request }, runFixture) => {
    await runFixture(new ProjectsAPI(request));
  },
  testProject: async ({ request }, runFixture) => {
    const projectDisplayName = generateTestResourceName('project');
    const projectDescription = `Project created by project.test.ts E2E test on ${CURRENT_YYYY_MM_DD}`;
    await testProjectFixture(
      request,
      runFixture,
      PROJECT_NAMESPACE,
      projectDisplayName,
      projectDescription
    );
  },
});

test.describe('Projects', () => {
  test.beforeEach(async ({ page }) => disableAuthForTest(page));
  // Each test should be responsible for deleting any resource it creates.
  // This clean-up step is just an extra measure to delete any projects that may have not have been successfully deleted.
  test.afterAll(async ({ projectsApi }) => {
    await projectsApi.deleteAllProjectsByWorkspace(PROJECT_NAMESPACE);
  });

  test('Creates a project', async ({ page, projectsPage, projectsApi }) => {
    test.slow();
    const projectDisplayName = generateTestResourceName('project');
    const projectDescription = `Project created by project.test.ts E2E test on ${CURRENT_YYYY_MM_DD}`;

    await projectsPage.goto();
    await projectsPage.waitForPageLoad();
    await projectsPage.createProject(projectDisplayName, projectDescription);

    // Expect to be redirected to landing page for project
    await page.waitForURL(INTAKE_ENABLED ? '**/dashboard' : '**/models');
    // Assert project is created and we are navigated to correct page
    const pathname = stripBasePath(new URL(page.url()).pathname);
    const pathMatch = matchPath({ path: PROJECT_LANDING_PAGE }, pathname);
    expect(pathMatch).toBeTruthy();
    expect(pathMatch!.params.workspace).toBeTruthy();
    await projectsPage.waitForPageLoad();
    await expect(page.locator(`button:has-text("${projectDisplayName}")`)).toBeInViewport({
      timeout: LONG_OPERATION_TIMEOUT,
    });
    if (INTAKE_ENABLED) {
      await expect(page.locator(`text="${projectDescription}"`)).toBeInViewport({
        timeout: LONG_OPERATION_TIMEOUT,
      });
    }

    // Clean up project
    await projectsApi.deleteProject('default', pathMatch!.params.workspace!);
  });

  test('Updates a project', async ({ projectsPage, testProject }) => {
    await projectsPage.goto();
    await projectsPage.waitForPageLoad();
    await projectsPage.updateProject(
      testProject.project.name!,
      testProject.project.description || 'Test description'
    );
  });

  test('Deletes a project', async ({ projectsPage, testProject }) => {
    await projectsPage.goto();
    await projectsPage.waitForPageLoad();
    await projectsPage.deleteProject(testProject.project.name!);
  });
});
