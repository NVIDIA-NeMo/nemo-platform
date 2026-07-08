// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DatasetsAPI } from '@e2e-tests/api/datasets';
import { EvaluationsAPI } from '@e2e-tests/api/evaluations';
import { ModelsAPI } from '@e2e-tests/api/models';
import { ProjectsAPI } from '@e2e-tests/api/projects';
import {
  CreateModelEntityRequest,
  ModelEntity,
  Project,
} from '@nemo/sdk/generated/platform/schema';
import { APIRequestContext } from '@playwright/test';

/** Dataset shape for e2e fixtures. */
type Dataset = { files_url?: string; name?: string; namespace?: string; [key: string]: unknown };
/** Evaluation config shape for e2e fixtures. */
type EvaluationConfig = Record<string, unknown>;
/** Evaluation config input for create. */
type EvaluationConfigInput = Record<string, unknown>;

export interface TestProjectFixture {
  project: Project;
}

/**
 * Common fixture that creates a test project to use for an individual test.
 * The test will receive an argument of type `TestProjectFixture`.
 * Deletes the project after the test runs.
 */
export const testProjectFixture = async (
  request: APIRequestContext,
  runFixture: (returnValue: TestProjectFixture) => Promise<void>,
  projectNamespace: string,
  projectDisplayName: string,
  projectDescription: string
) => {
  // Create a test project
  const projectsApi = new ProjectsAPI(request);
  const testProject = await projectsApi.createProject(projectNamespace, {
    name: projectDisplayName,
    description: projectDescription,
  });
  const projectName = testProject.name || '';

  // Execute test
  await runFixture({ project: testProject });

  // Clean up the test project
  await projectsApi.deleteProject(projectNamespace, projectName);
};

export interface TestModelFixture {
  project: Project;
  model: ModelEntity;
}

/**
 * Common fixture that creates a test model to use for an individual test.
 * The test will receive an argument of type `TestModelFixture`.
 * Deletes the model after the test runs.
 */
export const testModelFixture = async (
  request: APIRequestContext,
  runFixture: (returnValue: TestModelFixture) => Promise<void>,
  project: Project,
  workspace: string,
  modelRequestBody: CreateModelEntityRequest
) => {
  // Create a test model
  const modelsApi = new ModelsAPI(request);
  const testModel = await modelsApi.createModel(workspace, modelRequestBody);

  // Execute test
  await runFixture({
    project,
    model: testModel,
  });

  // Clean up the test model
  await modelsApi.deleteModel(testModel.workspace!, testModel.name!);
};

export interface TestDatasetFixture {
  project: Project;
  dataset: Dataset;
}

/**
 * Common fixture that creates a test dataset to use for an individual test.
 * The test will receive an argument of type `TestDatasetFixture`.
 * Deletes the dataset after the test runs.
 */
export const testDatasetFixture = async (
  request: APIRequestContext,
  runFixture: (returnValue: TestDatasetFixture) => Promise<void>,
  project: Project,
  datasetName: string,
  datasetNamespace: string,
  datasetDescription: string
) => {
  // Create a test dataset
  const datasetsApi = new DatasetsAPI(request);
  const testDataset = await datasetsApi.createDataset(
    datasetName,
    datasetNamespace,
    `${project.workspace}/${project.name}`,
    datasetDescription
  );

  // Execute test
  await runFixture({
    project,
    dataset: testDataset,
  });

  // Clean up dataset
  await datasetsApi.deleteDataset(datasetName, datasetNamespace);
};

export interface TestDatasetFilesFixture {
  project: Project;
  dataset: Dataset;
}

/**
 * Common fixture that uploads a file(s) to the given dataset.
 * The test will receive an argument of type `TestDatasetFilesFixture`.
 */
export const testDatasetFilesFixture = async (
  request: APIRequestContext,
  runFixture: (returnValue: TestDatasetFixture) => Promise<void>,
  project: Project,
  dataset: Dataset,
  files: {
    // Path to local test file
    testFilePath: string;
    // Folder in the dataset to upload the file
    datasetFolder?: string;
  }[]
) => {
  // Upload the file(s) to the dataset
  const datasetsApi = new DatasetsAPI(request);
  // NOTE: This seems to consistently fail if uploading files in parallel. Specifically, the third call to HF that
  // commits the file fails with a 500. Uploading files sequentially succeeds, so we intentionally do that here.
  for (const file of files) {
    await datasetsApi.uploadFile(dataset, file.testFilePath, file.datasetFolder);
  }

  // Execute test
  await runFixture({
    project,
    dataset,
  });
};

export interface TestEvaluationConfigFixture {
  project: Project;
  evaluationConfig: EvaluationConfig;
}

/**
 * Common fixture that creates an evaluation config.
 * The test will receive an argument of type `TestEvaluationConfigFixture`.
 */

export const testEvaluationConfigFixture = async (
  request: APIRequestContext,
  runFixture: (returnValue: TestEvaluationConfigFixture) => Promise<void>,
  project: Project,
  evaluationConfigRequestBody: EvaluationConfigInput
) => {
  // Create the evaluation config
  const evaluationsApi = new EvaluationsAPI(request);
  const evaluationConfig = await evaluationsApi.createEvaluationConfig(evaluationConfigRequestBody);

  // Execute test
  await runFixture({
    project,
    evaluationConfig,
  });

  // Clean up the evaluation config
  await evaluationsApi.deleteEvaluationConfig(
    String((evaluationConfig as { namespace?: string }).namespace ?? ''),
    String((evaluationConfig as { name?: string }).name ?? '')
  );
};
