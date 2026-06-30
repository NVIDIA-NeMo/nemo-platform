// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CustomizationsAPI } from '@e2e-tests/api/customizations';
import { ProjectsAPI } from '@e2e-tests/api/projects';
import { ProjectCustomizationsPage } from '@e2e-tests/pages/project-customizations';
import {
  CURRENT_YYYY_MM_DD,
  DEFAULT_BASE_MODEL,
  MOCKS_DIR,
  buildTestNamespace,
  generateShortTestResourceName,
  generateTestResourceName,
} from '@e2e-tests/utils/constants';
import {
  testCustomizationJobFixture,
  TestCustomizationJobFixture,
  testDatasetFilesFixture,
  TestDatasetFilesFixture,
  testDatasetFixture,
  TestDatasetFixture,
  testProjectFixture,
  TestProjectFixture,
} from '@e2e-tests/utils/fixtures';
import {
  disableAuthForTest,
  waitForLongOperation,
  waitForTaskCompletion,
} from '@e2e-tests/utils/pageUtils';
import { CustomizationJobRequest } from '@nemo/sdk/vendored/customizer/schema';
import { expect, test as baseTest } from '@playwright/test';
import path from 'path';

const ASYNC_JOB_TIMEOUT = 1000 * 60 * 10; // 10 minutes
// Path to mock files that the tests will upload
const TRAINING_FILE = 'sentiment/train.jsonl';
const VALIDATION_FILE = 'sentiment/validation.jsonl';

const NAMESPACE = buildTestNamespace('customization');
const OUTPUT_MODEL_NAME = generateTestResourceName('model');

interface TestFixtures {
  customizationsPage: ProjectCustomizationsPage;
  projectsApi: ProjectsAPI;
  customizationsApi: CustomizationsAPI;
  testProject: TestProjectFixture;
  testDataset: TestDatasetFixture;
  testCustomizationFiles: TestDatasetFilesFixture;
  testCustomizationJob: TestCustomizationJobFixture;
}

const test = baseTest.extend<TestFixtures>({
  customizationsPage: async ({ page }, runFixture) => {
    await runFixture(new ProjectCustomizationsPage(page));
  },
  projectsApi: async ({ request }, runFixture) => {
    await runFixture(new ProjectsAPI(request));
  },
  customizationsApi: async ({ request }, runFixture) => {
    await runFixture(new CustomizationsAPI(request));
  },
  testProject: async ({ request }, runFixture) => {
    const projectDisplayName = generateTestResourceName('project');
    const projectDescription = `Project created by customization.test.ts E2E test on ${CURRENT_YYYY_MM_DD}`;
    await testProjectFixture(
      request,
      runFixture,
      NAMESPACE,
      projectDisplayName,
      projectDescription
    );
  },
  testDataset: async ({ request, testProject }, runFixture) => {
    const datasetName = generateShortTestResourceName();
    const datasetDescription = `Dataset created by customization.test.ts E2E test on ${CURRENT_YYYY_MM_DD}`;
    await testDatasetFixture(
      request,
      runFixture,
      testProject.project,
      datasetName,
      NAMESPACE,
      datasetDescription
    );
  },
  testCustomizationFiles: async ({ request, testDataset }, runFixture) => {
    await testDatasetFilesFixture(request, runFixture, testDataset.project, testDataset.dataset, [
      {
        testFilePath: TRAINING_FILE,
        datasetFolder: 'training',
      },
      {
        testFilePath: VALIDATION_FILE,
        datasetFolder: 'validation',
      },
    ]);
  },
  testCustomizationJob: async ({ request, testCustomizationFiles }, runFixture) => {
    const jobDescription = `Customization job created by customization.test.ts E2E test on ${CURRENT_YYYY_MM_DD}`;
    const requestBody: CustomizationJobRequest = {
      description: jobDescription,
      project: `${testCustomizationFiles.project.workspace}/${testCustomizationFiles.project.name}`,
      spec: {
        model: 'meta/llama-3.3-70b-instruct@v1.0.0+A100',
        dataset: `fileset://${testCustomizationFiles.dataset.namespace}/${testCustomizationFiles.dataset.name}`,
        training: {
          type: 'sft',
          peft: {
            type: 'lora',
            rank: 8,
            alpha: 16,
            dropout: 0,
            merge: false,
            use_dora: false,
          },
        },
      },
    };
    await testCustomizationJobFixture(
      request,
      runFixture,
      testCustomizationFiles.project,
      requestBody
    );
  },
});

test.describe('Customizations', () => {
  test.beforeEach(async ({ page }) => disableAuthForTest(page));

  // Each test should be responsible for deleting any resource it creates.
  // This clean-up step is just an extra measure to delete any projects that may have not have been successfully deleted.
  test.afterAll(async ({ projectsApi }) => {
    await projectsApi.deleteAllProjectsByWorkspace(NAMESPACE);
  });

  test('Creates a customization job', async ({ page, customizationsPage, testDataset }) => {
    test.slow();
    const { project, dataset } = testDataset;
    await test.step('Navigate to customizations page and click "Customize a Model" button', async () => {
      await customizationsPage.goto(project.workspace!, project.name!);

      const newModelButton = page.getByRole('button', { name: 'Customize a Model' }).first();
      await newModelButton.click();
      await waitForLongOperation(page);
    });

    await test.step('Select base model', async () => {
      const modelSelect = page.getByTestId('base-model-select');
      await modelSelect.click();

      await page.getByTestId('model-filter').fill(DEFAULT_BASE_MODEL.split('/')[0]);
      await page.getByRole('listbox').getByText(DEFAULT_BASE_MODEL.split('/')[1]).first().click();
    });

    await test.step('Set output model name', async () => {
      const outputModelNameField = page.getByRole('textbox', { name: 'Output Model' });
      await outputModelNameField.fill(OUTPUT_MODEL_NAME);
    });

    await test.step('Upload dataset', async () => {
      const datasetButton = page.getByRole('button', { name: 'New Dataset' });
      await datasetButton.click();
      const datasetNameField = page.getByRole('textbox', { name: 'Name' });
      await datasetNameField.fill(dataset.name!);
      const datasetDescriptionField = page.getByRole('textbox', { name: 'Description' });
      await datasetDescriptionField.fill('A dataset created by E2E test suite.');
    });

    await test.step('Set Files for dataset', async () => {
      const fileSelectorText = 'Drop a file or click to select a file';
      const fileChooserPromise = page.waitForEvent('filechooser');
      await page.getByText(fileSelectorText).first().click();
      const trainingFileInput = await fileChooserPromise;
      await trainingFileInput.setFiles(path.resolve(MOCKS_DIR, 'sentiment/train.jsonl'));
      const fileChooserPromise2 = page.waitForEvent('filechooser');
      await page.getByText(fileSelectorText).first().click();
      const validationFileInput = await fileChooserPromise2;
      await validationFileInput.setFiles(path.resolve(MOCKS_DIR, 'sentiment/validation.jsonl'));
    });

    await test.step('Submit', async () => {
      // Submit!
      await page.getByRole('button', { name: 'Add to Customization' }).click();
      await expect(page.getByText('Successfully created dataset!')).toBeVisible({
        timeout: 60000,
      });
      // Small timeout to wait for form to be validated by useEffect
      await page.waitForTimeout(1000);
      await page.getByRole('button', { name: 'Create Customization' }).click();
    });

    await test.step('Expect the job to be created and redirected to details page', async () => {
      await expect(page.getByText('Training Progress')).toBeVisible({
        timeout: 100000,
      });
    });
  });

  // TODO: Skip because NIM bug prevents us from using customized models in inference requests.
  test.skip('Runs inference on customized model', async ({
    page,
    customizationsApi,
    testCustomizationJob,
  }) => {
    test.setTimeout(ASYNC_JOB_TIMEOUT);
    await waitForTaskCompletion({
      evaluate: async () => {
        const { status } = await customizationsApi.getCustomizationJobStatus(
          testCustomizationJob.customizationJob.id!
        );
        if (!status) return false;
        return status === 'completed';
      },
      timeout: ASYNC_JOB_TIMEOUT,
      page,
    });

    // Navigate to the models page and chat with the customized model
    await page.goto(`models`);

    // Select the model
    await page.getByText(testCustomizationJob.customizationJob.id!).click();
    const chatInput = page.getByRole('textbox', { name: 'taskPrompt' });
    chatInput.fill('How are you doing today?');
    await chatInput.press('Enter');
    await expect(page.getByText('Assistant')).toBeVisible();
  });
});
