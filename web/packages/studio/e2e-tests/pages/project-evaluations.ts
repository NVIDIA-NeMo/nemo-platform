// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { waitForLongOperation } from '@e2e-tests/utils/pageUtils';
import { expect, type Page } from '@playwright/test';

export class ProjectEvaluationsPage {
  constructor(public readonly page: Page) {}

  async gotoEvaluations(projectNamespace: string, projectName: string) {
    await this.page.goto(`projects/${projectNamespace}/${projectName}/evaluation/jobs`);
  }

  async goToEvaluationConfigs(projectNamespace: string, projectName: string) {
    await this.page.goto(`projects/${projectNamespace}/${projectName}/evaluation/configurations`);
  }

  async waitForPageLoad() {
    await waitForLongOperation(this.page);
  }

  /**
   * Selects a file from the file picker modal.
   * Assumes the modal is already open (after clicking "Select File" button).
   *
   * @param datasetName - Name of the dataset to select from the dropdown
   * @param fileNamePattern - Pattern to match the file row (string or RegExp)
   */
  async selectFileFromModal(datasetName: string, fileNamePattern: string | RegExp) {
    // Select the dataset from the dropdown
    await this.page.getByRole('combobox', { name: 'Dataset' }).click();
    const datasetOption = this.page.getByRole('option', { name: datasetName });
    await datasetOption.click();

    // Wait for spinner to hide
    await this.page.getByTestId('nv-spinner-spinner').waitFor({ state: 'hidden' });

    // Select the file
    const fileCheckbox = this.page
      .getByRole('row', { name: fileNamePattern })
      .getByTestId('nv-checkbox-box');
    await fileCheckbox.click();

    // Confirm selection
    await this.page.getByRole('button', { name: 'Add selected file' }).click();
  }

  /**
   * Selects an evaluation configuration from the configuration dropdown.
   *
   * @param configName - Name of the configuration to select
   */
  async selectConfiguration(configName: string) {
    const configSelectTrigger = this.page.getByRole('combobox', {
      name: 'Evaluation Configuration',
    });
    await expect(configSelectTrigger).not.toBeDisabled();
    await configSelectTrigger.click();

    // Wait for the option to be visible before clicking
    const configOption = this.page.getByRole('option', { name: configName });
    await expect(configOption).toBeVisible();
    await configOption.click();

    // Verify the selection was successful by checking the dropdown now shows the config name
    await expect(configSelectTrigger).toContainText(configName);
  }

  /**
   * Clicks the create evaluation job button and verifies navigation to the job details page.
   *
   * @param buttonName - Name of the create button (defaults to 'Create Evaluation Job')
   */
  async createJobAndVerify(buttonName: string = 'Create Evaluation Job') {
    await this.page.getByRole('button', { name: buttonName }).click();

    // Wait for navigation to the job details page
    await this.page.waitForURL(/\/evaluation\/jobs\/eval-/);

    // Verify we're on the job details page by checking for unique elements
    await expect(this.page.getByText('Configuration Details')).toBeVisible();
    await expect(this.page.getByText('Status Logs')).toBeVisible();
    await expect(this.page.getByText('Evaluations')).toBeVisible();
  }
}
