// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { formatAbsoluteTimestamp } from '@nemo/common/src/components/RelativeTime/util';
import { getEntityReference } from '@nemo/common/src/namedEntity';
import { PlatformJobResponse, PlatformJobStatus } from '@nemo/sdk/generated/platform/schema';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { customizationJob1 } from '@studio/mocks/customizer/customization-jobs';
import { dataset } from '@studio/mocks/datasets';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { server } from '@studio/mocks/node';
import { CustomizationJobDetailsRoute } from '@studio/routes/CustomizationJobDetailsRoute';
import { XL_SELECTOR_TIMEOUT } from '@studio/tests/util/constants';
import { mockUseNavigate, mockUseParams } from '@studio/tests/util/mockUseParams';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { getBaseModel } from '@studio/util/customizations';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

describe('CustomizationJobDetailsRoute', () => {
  beforeEach(() => {
    mockUseNavigate();
    mockUseParams({
      [ROUTE_PARAMS.workspace]: workspace1.name,
      [ROUTE_PARAMS.customizationJobName]: customizationJob1.name,
    });
  });

  afterEach(() => {
    server.resetHandlers();
  });
  it('should render customization details', async () => {
    render(
      <TestProviders>
        <CustomizationJobDetailsRoute />
      </TestProviders>
    );

    // Use longer timeout
    expect(
      (await screen.findAllByText(customizationJob1.id!, {}, { timeout: XL_SELECTOR_TIMEOUT }))
        .length
    ).toBeGreaterThan(0);
    expect(
      (
        await screen.findAllByText(
          getEntityReference(dataset),
          {},
          { timeout: XL_SELECTOR_TIMEOUT }
        )
      ).length
    ).toBeGreaterThan(0);
    expect(screen.queryByTestId('customization-error-banner')).not.toBeInTheDocument();
  });

  it('names the job in the page header with its type, base model, and created date', async () => {
    render(
      <TestProviders>
        <CustomizationJobDetailsRoute />
      </TestProviders>
    );

    expect(
      await screen.findByText('LoRA', {}, { timeout: XL_SELECTOR_TIMEOUT })
    ).toBeInTheDocument();

    expect(screen.getByText(customizationJob1.name!)).toBeInTheDocument();
    expect(screen.getAllByText(getBaseModel(customizationJob1)).length).toBeGreaterThan(0);
    expect(
      screen.getByText(`created ${formatAbsoluteTimestamp(customizationJob1.created_at!)}`)
    ).toBeInTheDocument();
  });

  it('keeps polling an active job after switching away from the Overview tab', async () => {
    let jobRequests = 0;
    server.use(
      http.get<never, never, PlatformJobResponse>(
        `${PLATFORM_BASE_URL}/apis/jobs/v2/workspaces/:workspace/jobs/:name`,
        () => {
          jobRequests += 1;
          return HttpResponse.json({
            ...customizationJob1,
            status: PlatformJobStatus.active,
          } as unknown as PlatformJobResponse);
        }
      )
    );

    const user = userEvent.setup();
    render(
      <TestProviders>
        <CustomizationJobDetailsRoute />
      </TestProviders>
    );

    await user.click(await screen.findByRole('tab', { name: /Logs/ }));
    expect(screen.queryByText('Run configuration')).not.toBeInTheDocument();

    const requestsAfterSwitch = jobRequests;
    await waitFor(() => expect(jobRequests).toBeGreaterThan(requestsAfterSwitch), {
      timeout: XL_SELECTOR_TIMEOUT,
    });
  });

  it('shows the job logs in their own tab', async () => {
    server.use(
      http.get(`${PLATFORM_BASE_URL}/apis/jobs/v2/workspaces/:workspace/jobs/:name/logs`, () =>
        HttpResponse.json({
          data: [
            {
              timestamp: '2025-10-24T15:13:17Z',
              job: customizationJob1.name,
              job_step: 'training',
              job_task: 'main',
              message: 'The training job is pending',
            },
          ],
          total: 1,
          next_page: '',
          prev_page: '',
        })
      )
    );

    const user = userEvent.setup();
    render(
      <TestProviders>
        <CustomizationJobDetailsRoute />
      </TestProviders>
    );

    await user.click(await screen.findByRole('tab', { name: /Logs/ }));

    await waitFor(
      () => {
        expect(
          screen.getByText((content) => content.includes('The training job is pending'))
        ).toBeInTheDocument();
      },
      { timeout: XL_SELECTOR_TIMEOUT }
    );
  });

  it('Should render error message for a failed customization', async () => {
    const user = userEvent.setup();
    const mockErrorDetail =
      'CUDA out of memory. Tried to allocate 896.00 MiB. GPU 1 has a total capacity of 79.32 GiB of which 185.56 MiB is free.';

    server.use(
      http.get<never, never, PlatformJobResponse>(
        `${PLATFORM_BASE_URL}/apis/jobs/v2/workspaces/:workspace/jobs/:name`,
        () => {
          return HttpResponse.json({
            ...customizationJob1,
            status: PlatformJobStatus.error,
            status_details: {
              created_at: customizationJob1.created_at!,
              updated_at: customizationJob1.updated_at!,
              status: 'failed',
              status_logs: [
                {
                  updated_at: customizationJob1.updated_at!,
                  message: 'TraingJobFailed',
                  detail: mockErrorDetail,
                },
              ],
            },
          } as unknown as PlatformJobResponse);
        }
      ),
      http.get(`${PLATFORM_BASE_URL}/apis/jobs/v2/workspaces/:workspace/jobs/:name/logs`, () =>
        HttpResponse.json({
          data: [
            {
              timestamp: customizationJob1.updated_at!,
              job: customizationJob1.name,
              job_step: 'training',
              job_task: 'main',
              message: mockErrorDetail,
            },
          ],
          total: 1,
          next_page: '',
          prev_page: '',
        })
      )
    );

    render(
      <TestProviders>
        <CustomizationJobDetailsRoute />
      </TestProviders>
    );

    // Ensure status is error (PlatformJobStatus.error displays as "Error")
    expect(
      await screen.findByText('Error', undefined, { timeout: XL_SELECTOR_TIMEOUT })
    ).toBeInTheDocument();

    await user.click(await screen.findByRole('tab', { name: /Logs/ }));

    await waitFor(
      () => {
        expect(screen.getByText(/CUDA out of memory/)).toBeInTheDocument();
      },
      { timeout: XL_SELECTOR_TIMEOUT }
    );
  });
});
