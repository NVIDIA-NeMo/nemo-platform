// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { NMP_BASE_URL } from '@e2e-tests/utils/environment';
import {
  CustomizationJob as CustomizationJobOutput,
  CustomizationJobRequest as CustomizationJobInput,
  CustomizationJobStatusDetails as CustomizationStatusDetails,
} from '@nemo/sdk/vendored/customizer/schema';
import { APIRequestContext } from '@playwright/test';

export class CustomizationsAPI {
  constructor(private request: APIRequestContext) {}

  async createCustomizationJob(data: CustomizationJobInput) {
    const response = await this.request.post(`${NMP_BASE_URL}/v1/customization/jobs`, {
      data,
    });
    const responseData = (await response.json()) as CustomizationJobOutput;
    return responseData;
  }

  async getCustomizationJobStatus(jobId: string) {
    const response = await this.request.get(
      `${NMP_BASE_URL}/v1/customization/jobs/${jobId}/status`
    );
    const responseData = (await response.json()) as CustomizationStatusDetails;
    return responseData;
  }
}
