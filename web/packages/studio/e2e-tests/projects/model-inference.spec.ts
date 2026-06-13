// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ModelsAPI } from '@e2e-tests/api/models';
import { ProjectsAPI } from '@e2e-tests/api/projects';
import { ProjectModelsPage } from '@e2e-tests/pages/project-models';
import {
  buildTestNamespace,
  CURRENT_HH_MM_SS,
  CURRENT_YYYY_MM_DD,
  DEFAULT_BASE_MODEL,
  generateTestResourceName,
} from '@e2e-tests/utils/constants';
import {
  TestProjectFixture,
  TestModelFixture,
  testProjectFixture,
  testModelFixture,
} from '@e2e-tests/utils/fixtures';
import { expectChatResponseToContain } from '@e2e-tests/utils/models';
import { disableAuthForTest } from '@e2e-tests/utils/pageUtils';
import { CreateModelEntityRequest } from '@nemo/sdk/generated/platform/schema';
import { test as baseTest } from '@playwright/test';

const NAMESPACE = buildTestNamespace('model-inference');
const MODEL_SYNC_WAIT_TIME_MS = 5.5 * 60 * 1000; // 7 minutes

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
    const projectDescription = `Project created by model-inference.test.ts E2E test on ${CURRENT_YYYY_MM_DD}`;
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

test.describe('Projects Model Inference', () => {
  test.describe.configure({ retries: 0 });
  test.beforeEach(async ({ page }) => disableAuthForTest(page));

  // Each test should be responsible for deleting any project it creates.
  // This clean-up step is just an extra measure to delete any projects that may have not have been successfully deleted.
  test.afterAll(async ({ projectsApi }) => {
    await projectsApi.deleteAllProjectsByWorkspace(NAMESPACE);
  });

  test('Base model inference with no settings', async ({
    page,
    projectModelsPage,
    modelsApi,
    testProject,
  }) => {
    test.setTimeout(MODEL_SYNC_WAIT_TIME_MS + 60 * 1000);
    const modelName = `E2E_MODEL_${CURRENT_YYYY_MM_DD}_${CURRENT_HH_MM_SS()}`;
    await projectModelsPage.goto(testProject.project.workspace!, testProject.project.name!);
    await projectModelsPage.waitForPageLoad();
    await projectModelsPage.createModel({
      modelName,
      projectNamespace: testProject.project.workspace!,
    });

    // In the background, NIM periodically fetches newly-created models.
    // Wait before trying to run inference on this model.
    await page.waitForSelector('textarea[aria-label="Task prompt"]:not([disabled])', {
      timeout: MODEL_SYNC_WAIT_TIME_MS,
    });

    // Chat with model
    await page
      .getByRole('textbox', { name: 'Task prompt' })
      .fill('What is the capital of Washington state?');
    await page.getByRole('button', { name: 'Submit' }).click();

    await expectChatResponseToContain(page, 'Olympia');

    // Clean up model
    await modelsApi.deleteModel('default', modelName);
  });

  test('Base model inference with system prompt and ICL', async ({
    page,
    projectModelsPage,
    testProject,
  }) => {
    test.setTimeout(MODEL_SYNC_WAIT_TIME_MS + 60 * 1000);
    const modelName = `E2E_MODEL_${CURRENT_YYYY_MM_DD}_${CURRENT_HH_MM_SS()}`;
    await projectModelsPage.goto(testProject.project.workspace!, testProject.project.name!);
    await projectModelsPage.waitForPageLoad();

    const systemPromptTemplate = `You will respond to every question with a single word: potato
        {{icl_few_shot_examples}}`;
    const iclFewShotExamples = new File(
      [
        `
        {"question": "What is the capital of Mongolia?", "answer": "potato"}
        {"question": "What is the current date?", "answer": "potato"}
        {"question": "What is the capital of Washington state?", "answer": "potato"}
        `,
      ],
      'icl-few-shot-examples.jsonl',
      { type: 'application/json' }
    );
    await projectModelsPage.createModel({
      modelName,
      systemPromptTemplate,
      iclFewShotExamples,
      projectNamespace: testProject.project.workspace!,
    });

    await page.waitForSelector('textarea[aria-label="Task prompt"]:not([disabled])', {
      timeout: MODEL_SYNC_WAIT_TIME_MS,
    });

    await page
      .getByRole('textbox', { name: 'Task prompt' })
      .fill('What is the capital of Washington state?');
    await page.getByRole('button', { name: 'Submit' }).click();
    await expectChatResponseToContain(page, 'potato');
  });
});
