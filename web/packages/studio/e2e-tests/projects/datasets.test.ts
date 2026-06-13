// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DatasetsAPI } from '@e2e-tests/api/datasets';
import { ProjectsAPI } from '@e2e-tests/api/projects';
import { ProjectDatasetsPage } from '@e2e-tests/pages/project-datasets';
import {
  CURRENT_YYYY_MM_DD,
  buildTestNamespace,
  generateTestResourceName,
} from '@e2e-tests/utils/constants';
import {
  testDatasetFilesFixture,
  TestDatasetFilesFixture,
  testDatasetFixture,
  TestDatasetFixture,
  testProjectFixture,
  TestProjectFixture,
} from '@e2e-tests/utils/fixtures';
import { disableAuthForTest } from '@e2e-tests/utils/pageUtils';
import { expect, test as baseTest } from '@playwright/test';

// Path to mock files that the tests will upload
const TRAINING_FILE = 'sentiment/train.jsonl';
const VALIDATION_FILE = 'sentiment/validation.jsonl';

const NAMESPACE = buildTestNamespace('datasets');
interface TestFixtures {
  datasetsPage: ProjectDatasetsPage;
  projectsApi: ProjectsAPI;
  datasetsApi: DatasetsAPI;
  testProject: TestProjectFixture;
  testDataset: TestDatasetFixture;
  testTrainingFile: TestDatasetFilesFixture;
}

const test = baseTest.extend<TestFixtures>({
  datasetsPage: async ({ page }, runFixture) => {
    await runFixture(new ProjectDatasetsPage(page));
  },
  projectsApi: async ({ request }, runFixture) => {
    await runFixture(new ProjectsAPI(request));
  },
  datasetsApi: async ({ request }, runFixture) => {
    await runFixture(new DatasetsAPI(request));
  },
  testProject: async ({ request }, runFixture) => {
    const projectDisplayName = generateTestResourceName('project');
    const projectDescription = `Project created by datasets.test.ts E2E test on ${CURRENT_YYYY_MM_DD}`;
    await testProjectFixture(
      request,
      runFixture,
      NAMESPACE,
      projectDisplayName,
      projectDescription
    );
  },
  testDataset: async ({ request, testProject }, runFixture) => {
    const datasetName = generateTestResourceName('dataset');
    const datasetDescription = `Dataset created by datasets.test.ts E2E test on ${CURRENT_YYYY_MM_DD}`;
    await testDatasetFixture(
      request,
      runFixture,
      testProject.project,
      datasetName,
      NAMESPACE,
      datasetDescription
    );
  },
  testTrainingFile: async ({ request, testDataset }, runFixture) => {
    await testDatasetFilesFixture(request, runFixture, testDataset.project, testDataset.dataset, [
      {
        testFilePath: TRAINING_FILE,
        datasetFolder: 'training',
      },
    ]);
  },
});

test.describe('Projects: Datasets', () => {
  test.beforeEach(async ({ page }) => disableAuthForTest(page));
  // Each test should be responsible for deleting any project it creates.
  // This clean-up step is just an extra measure to delete any projects that may have not have been successfully deleted.
  test.afterAll(async ({ projectsApi }) => {
    await projectsApi.deleteAllProjectsByWorkspace(NAMESPACE);
  });

  test('Should render list of datasets', async ({ page, datasetsPage, testDataset }) => {
    await datasetsPage.goto(testDataset.project.workspace!, testDataset.project.name!);
    await datasetsPage.waitForPageLoad();
    await expect(page.getByText(testDataset.dataset.name!)).toBeVisible();
    await expect(
      page.getByText(String((testDataset.dataset as { description?: string }).description ?? ''))
    ).toBeVisible();
  });

  test('Should successfully upload training file', async ({ page, datasetsPage, testDataset }) => {
    test.slow();
    await datasetsPage.goto(
      testDataset.project.workspace!,
      testDataset.project.name!,
      testDataset.dataset
    );
    await datasetsPage.waitForPageLoad();
    expect(page.getByText('No files')).toBeVisible();
    await datasetsPage.uploadFileToDataset(TRAINING_FILE);
  });

  test('Should successfully upload validation file', async ({
    page,
    datasetsPage,
    testDataset,
  }) => {
    test.slow();
    await datasetsPage.goto(
      testDataset.project.workspace!,
      testDataset.project.name!,
      testDataset.dataset
    );
    await datasetsPage.waitForPageLoad();
    expect(page.getByText('No files')).toBeVisible();
    await datasetsPage.uploadFileToDataset(VALIDATION_FILE);
  });

  test('Should successfully delete file', async ({ datasetsPage, testTrainingFile }) => {
    test.slow();
    await datasetsPage.goto(
      testTrainingFile.project.workspace!,
      testTrainingFile.project.name!,
      testTrainingFile.dataset
    );
    await datasetsPage.waitForPageLoad();
    await datasetsPage.deleteFileFromDataset('training/train.jsonl');
  });

  test('Should successfully rename file', async ({ datasetsPage, testTrainingFile }) => {
    test.slow();
    await datasetsPage.goto(
      testTrainingFile.project.workspace!,
      testTrainingFile.project.name!,
      testTrainingFile.dataset
    );
    await datasetsPage.waitForPageLoad();

    await datasetsPage.renameFileInDataset('training/train.jsonl', 'renamed-train.jsonl');
  });

  test('Should successfully delete a dataset', async ({ datasetsPage, testDataset }) => {
    await datasetsPage.goto(testDataset.project.workspace!, testDataset.project.name!);
    await datasetsPage.waitForPageLoad();
    await datasetsPage.deleteDataset(testDataset.dataset.name!);
  });
});
