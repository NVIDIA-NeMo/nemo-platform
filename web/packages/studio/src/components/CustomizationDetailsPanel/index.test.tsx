// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { formatAbsoluteTimestamp } from '@nemo/common/src/components/RelativeTime/util';
import type { PlatformJobLogPage } from '@nemo/sdk/generated/platform/schema';
import { CustomizationDetailsPanel } from '@studio/components/CustomizationDetailsPanel';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { customizationJob1 } from '@studio/mocks/customizer/customization-jobs';
import { server } from '@studio/mocks/node';
import { XL_SELECTOR_TIMEOUT } from '@studio/tests/util/constants';
import { TestProviders } from '@studio/tests/util/TestProviders';
import {
  getCustomizationConfigurationName,
  getCustomizationTrainingProgress,
} from '@studio/util/customizations';
import { render, screen, waitFor, waitForElementToBeRemoved } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

describe('CustomizationDetailsPanel', () => {
  it('should render customization details', async () => {
    render(
      <TestProviders>
        <CustomizationDetailsPanel
          customizationJobName={customizationJob1.name!}
          workspace={customizationJob1.workspace}
        />
      </TestProviders>
    );
    await waitForElementToBeRemoved(() => screen.queryByText('Loading...'), {
      timeout: XL_SELECTOR_TIMEOUT,
    });

    expect(screen.getByText('Training Progress')).toBeInTheDocument();
    expect(await screen.findByText('Status')).toBeInTheDocument();

    expect(screen.getByText('Epochs Completed')).toBeInTheDocument();
    expect(
      screen.getByText(getCustomizationTrainingProgress(customizationJob1))
    ).toBeInTheDocument();

    expect(screen.getByText('Customization ID')).toBeInTheDocument();
    expect(screen.getByText(customizationJob1.id!)).toBeInTheDocument();

    expect(screen.getByText('Output Model')).toBeInTheDocument();
    expect(screen.getByText(customizationJob1.spec?.output?.name ?? '-')).toBeInTheDocument();

    expect(screen.getByText('Configuration')).toBeInTheDocument();
    expect(
      screen.getByText(getCustomizationConfigurationName(customizationJob1.spec?.model) ?? '-')
    ).toBeInTheDocument();

    expect(screen.getByText('Description')).toBeInTheDocument();
    expect(screen.getByText(customizationJob1.description!)).toBeInTheDocument();

    expect(screen.getByText('Created')).toBeInTheDocument();
    expect(
      screen.getByText(
        customizationJob1.created_at ? formatAbsoluteTimestamp(customizationJob1.created_at) : '-'
      )
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'View Job Configuration' })).toBeInTheDocument();
  });

  it('should show status logs when clicking the accordion trigger', async () => {
    server.use(
      http.get<never, never, PlatformJobLogPage>(
        `${PLATFORM_BASE_URL}/apis/jobs/v2/workspaces/:workspace/jobs/:name/logs`,
        () =>
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
        <CustomizationDetailsPanel
          customizationJobName={customizationJob1.name!}
          workspace={customizationJob1.workspace}
        />
      </TestProviders>
    );
    await waitForElementToBeRemoved(() => screen.queryByText('Loading...'), {
      timeout: XL_SELECTOR_TIMEOUT,
    });

    await screen.findByText('Status');
    const accordionTrigger = screen.getByText('Status Logs');
    await user.click(accordionTrigger);

    await waitFor(() => {
      expect(
        screen.getByText((content) => content.includes('The training job is pending'))
      ).toBeInTheDocument();
    });
  });
});
