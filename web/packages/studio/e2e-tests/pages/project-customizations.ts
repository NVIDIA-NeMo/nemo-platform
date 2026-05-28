// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CustomizationJob as CustomizationJobOutput } from '@nemo/sdk/vendored/customizer/schema';
import { type Page } from '@playwright/test';

export class ProjectCustomizationsPage {
  constructor(public readonly page: Page) {}

  async goto(
    projectNamespace: string,
    projectName: string,
    customizationJob?: CustomizationJobOutput
  ) {
    const jobIdParam = customizationJob ? `/${customizationJob.id}` : '';
    await this.page.goto(`projects/${projectNamespace}/${projectName}/customizations${jobIdParam}`);
  }
}
