// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ModelsAPI } from '@e2e-tests/api/models';
import { ProjectsAPI } from '@e2e-tests/api/projects';
import { ProjectModelsPage } from '@e2e-tests/pages/project-models';
import {
  CURRENT_YYYY_MM_DD,
  DEFAULT_BASE_MODEL,
  buildTestNamespace,
  generateTestResourceName,
} from '@e2e-tests/utils/constants';
import {
  testModelFixture,
  TestModelFixture,
  TestProjectFixture,
  testProjectFixture,
} from '@e2e-tests/utils/fixtures';
import { disableAuthForTest } from '@e2e-tests/utils/pageUtils';
import { CreateModelEntityRequest } from '@nemo/sdk/generated/platform/schema';
import { test as baseTest } from '@playwright/test';

// Namespace for test resources created by this test suite's fixtures
const NAMESPACE = buildTestNamespace('model');

interface TestFixtures {
  projectModelsPage: ProjectModelsPage;
  modelsApi: ModelsAPI;
  projectsApi: ProjectsAPI;
  testProject: TestProjectFixture;
  testModel: TestModelFixture;
}

const test = baseTest.extend<TestFixtures>({
  projectModelsPage: async ({ page }, runFixture) => {
    await runFixture(new ProjectModelsPage(page));
  },
  modelsApi: async ({ request }, runFixture) => {
    await runFixture(new ModelsAPI(request));
  },
  projectsApi: async ({ request }, runFixture) => {
    await runFixture(new ProjectsAPI(request));
  },
  testProject: async ({ request }, runFixture) => {
    const projectDisplayName = generateTestResourceName('project');
    const projectDescription = `Project created by model.test.ts E2E test on ${CURRENT_YYYY_MM_DD}`;
    await testProjectFixture(
      request,
      runFixture,
      NAMESPACE,
      projectDisplayName,
      projectDescription
    );
  },
  testModel: async ({ request, testProject }, runFixture) => {
    const createModelBody: CreateModelEntityRequest = {
      base_model: DEFAULT_BASE_MODEL,
      name: generateTestResourceName('model'),
      project: `${testProject.project.workspace}/${testProject.project.name}`,
      prompt: {
        system_prompt: '',
        icl_few_shot_examples: '{{icl_few_shot_examples}}',
      },
    };
    await testModelFixture(request, runFixture, testProject.project, NAMESPACE, createModelBody);
  },
});

test.describe('Projects: Models', () => {
  test.beforeEach(async ({ page }) => disableAuthForTest(page));
  // Each test should be responsible for deleting any project it creates.
  // This clean-up step is just an extra measure to delete any projects that may have not have been successfully deleted.
  test.afterAll(async ({ projectsApi }) => {
    await projectsApi.deleteAllProjectsByWorkspace(NAMESPACE);
  });

  test('Create a model', async ({ projectModelsPage, modelsApi, testProject }) => {
    test.slow();
    const modelName = generateTestResourceName('model');

    await projectModelsPage.goto(testProject.project.workspace!, testProject.project.name!);
    await projectModelsPage.waitForPageLoad();
    await projectModelsPage.createModel({
      modelName,
      projectNamespace: testProject.project.workspace!,
    });

    // Clean up model
    // NOTE: When creating a model from Studio, the namespace is always `default`
    await modelsApi.deleteModel('default', modelName);
  });

  test('Delete a model', async ({ projectModelsPage, testModel }) => {
    await projectModelsPage.goto(testModel.project.workspace!, testModel.project.name!);
    await projectModelsPage.waitForPageLoad();
    await projectModelsPage.deleteModel(`${testModel.model.workspace}/${testModel.model.name}`);
  });
});
