// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PlatformJobStatus } from '@nemo/sdk/generated/platform/schema';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { customizationJob1 } from '@studio/mocks/customizer/customization-jobs';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { server } from '@studio/mocks/node';
import { DetailActions } from '@studio/routes/CustomizationJobDetailsRoute/DetailActions';
import { mockUseNavigate, mockUseParams } from '@studio/tests/util/mockUseParams';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { delay, http, HttpResponse } from 'msw';

describe('DetailActions', () => {
  beforeEach(() => {
    mockUseNavigate();
    mockUseParams({
      [ROUTE_PARAMS.workspace]: workspace1.name,
      [ROUTE_PARAMS.customizationJobId]: customizationJob1.id,
    });
  });
  it('should render cancel button when status is cancellable', () => {
    render(
      <TestProviders>
        <DetailActions status={PlatformJobStatus.created} />
      </TestProviders>
    );
    expect(screen.getByRole('button', { name: 'Cancel Job' })).toBeEnabled();
  });
  it('should render evaluate button when status is launchable', () => {
    render(
      <TestProviders>
        <DetailActions status={PlatformJobStatus.completed} />
      </TestProviders>
    );
    expect(screen.getByRole('button', { name: 'Evaluate' })).toBeEnabled();
  });
  it('should render loading button when mutation is pending', async () => {
    // Override the default handler with an infinite delay to capture the loading state
    server.use(
      http.post(
        `${PLATFORM_BASE_URL}/apis/customization/v2/workspaces/:workspace/jobs/:name/cancel`,
        async () => {
          await delay('infinite'); // Delay indefinitely to ensure loading state is captured
          return HttpResponse.json(customizationJob1);
        }
      )
    );

    const user = userEvent.setup();
    render(
      <TestProviders>
        <DetailActions status={PlatformJobStatus.created} />
      </TestProviders>
    );

    await user.click(screen.getByRole('button', { name: 'Cancel Job' }));

    // Wait for the loading state to appear (Spinner has role="status")
    expect(await screen.findByRole('status')).toBeInTheDocument();
  });
  it.each([
    PlatformJobStatus.cancelled,
    PlatformJobStatus.error, // Platform uses 'error' instead of 'failed'
    PlatformJobStatus.paused, // Platform doesn't have 'unknown', using 'paused' instead
  ])('should render nothing when status is %s', (status) => {
    render(
      <TestProviders>
        <DetailActions status={status} />
      </TestProviders>
    );
    expect(screen.queryByRole('button', { name: 'Cancel Job' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Evaluate' })).not.toBeInTheDocument();
  });
});
