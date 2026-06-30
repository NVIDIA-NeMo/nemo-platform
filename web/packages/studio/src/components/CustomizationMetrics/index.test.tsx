// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PlatformJobStatusResponse } from '@nemo/sdk/generated/platform/schema';
import { CustomizationMetrics } from '@studio/components/CustomizationMetrics';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { customizationJob1 } from '@studio/mocks/customizer/customization-jobs';
import { server } from '@studio/mocks/node';
import { render } from '@studio/tests/util/render';
import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';

describe('CustomizationMetrics', () => {
  it('renders the empty state when there are no metrics', async () => {
    server.use(
      http.get(
        `${PLATFORM_BASE_URL}/apis/customization/v2/workspaces/:workspace/jobs/:name/status`,
        () =>
          HttpResponse.json({
            id: customizationJob1.id,
            name: customizationJob1.name,
            status: customizationJob1.status,
            status_details: { ...customizationJob1.status_details, metrics: undefined },
          } as unknown as PlatformJobStatusResponse)
      )
    );
    render(
      <CustomizationMetrics
        customizationJobId={customizationJob1.id!}
        workspace={customizationJob1.workspace}
      />
    );

    expect(await screen.findByText('No activity')).toBeInTheDocument();
  });

  it('renders sections for each metric', async () => {
    render(
      <CustomizationMetrics
        customizationJobId={customizationJob1.id!}
        workspace={customizationJob1.workspace}
      />
    );

    expect(await screen.findByRole('heading', { name: 'Training Loss' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Validation Loss' })).toBeInTheDocument();
  });
});
