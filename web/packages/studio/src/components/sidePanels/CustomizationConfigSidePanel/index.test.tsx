// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CustomizationConfigSidePanel } from '@studio/components/sidePanels/CustomizationConfigSidePanel';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { customizationJob1, customizationJob2 } from '@studio/mocks/customizer/customization-jobs';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { server } from '@studio/mocks/node';
import { getWorkspaceCustomizationJobDetailsRoute } from '@studio/routes/utils';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { getBaseModel, getFormattedTrainingType } from '@studio/util/customizations';
import { render, screen } from '@testing-library/react';
import { delay, http, HttpResponse } from 'msw';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

const GENERIC_JOB_URL = `${PLATFORM_BASE_URL}/apis/jobs/v2/workspaces/:workspace/jobs/:name`;

const renderPanel = () => {
  const router = createMemoryRouter(
    [
      {
        path: ROUTES.workspace.customizationJobDetails,
        element: (
          <CustomizationConfigSidePanel
            open
            customizationJobName={customizationJob1.name!}
            workspace={workspace1.workspace}
          />
        ),
      },
    ],
    {
      initialEntries: [
        getWorkspaceCustomizationJobDetailsRoute(workspace1.workspace, customizationJob1.name!),
      ],
    }
  );
  return render(
    <TestProviders>
      <RouterProvider router={router} />
    </TestProviders>
  );
};

describe('CustomizationConfigSidePanel', () => {
  it('should render loading state when loading', async () => {
    server.use(
      http.get(GENERIC_JOB_URL, async () => {
        await delay('infinite');
        return HttpResponse.json(customizationJob1);
      })
    );
    renderPanel();
    expect(await screen.findByText('Loading...')).toBeInTheDocument();
  });

  it('should render customization configuration details', async () => {
    // Automodel SFT + LoRA job exercises the full set of automodel hyperparameter rows.
    const job = customizationJob2;
    server.use(http.get(GENERIC_JOB_URL, () => HttpResponse.json(job)));

    renderPanel();

    expect(screen.getByText('Customization Configuration')).toBeInTheDocument();
    expect(await screen.findByText('Name')).toBeInTheDocument();
    expect(screen.getByText(job.spec.output.name)).toBeInTheDocument();

    expect(screen.getByText('Configuration Snapshot')).toBeInTheDocument();
    expect(screen.getByText('Base Model')).toBeInTheDocument();
    expect(screen.getAllByText(getBaseModel(job)).length).toBeGreaterThan(0);

    expect(screen.getByText('Training Type')).toBeInTheDocument();
    expect(screen.getByText(getFormattedTrainingType('sft'))).toBeInTheDocument();
    expect(screen.getByText('Finetuning Type')).toBeInTheDocument();
    expect(screen.getByText(getFormattedTrainingType('lora'))).toBeInTheDocument();
    expect(screen.getByText('Training Options')).toBeInTheDocument();

    expect(screen.getByText('Hyperparameters')).toBeInTheDocument();
    expect(screen.getByText('Epochs')).toBeInTheDocument();
    expect(screen.getByText('Max Steps')).toBeInTheDocument();
    expect(screen.getByText(String(job.spec.schedule.max_steps))).toBeInTheDocument();
    expect(screen.getByText('Learning Rate')).toBeInTheDocument();
    expect(screen.getByText(String(job.spec.optimizer.learning_rate))).toBeInTheDocument();
    expect(screen.getByText('Global Batch Size')).toBeInTheDocument();
    expect(screen.getByText(String(job.spec.batch.global_batch_size))).toBeInTheDocument();
    expect(screen.getByText('Micro Batch Size')).toBeInTheDocument();

    expect(screen.getByText('LoRA / Rank')).toBeInTheDocument();
    expect(screen.getByText(String(job.spec.training.lora!.rank))).toBeInTheDocument();
    expect(screen.getByText('LoRA / Alpha')).toBeInTheDocument();
    expect(screen.getByText('LoRA / Target Modules')).toBeInTheDocument();
    expect(
      screen.getByText(job.spec.training.lora!.target_modules!.join(', '))
    ).toBeInTheDocument();
  });

  it('should render error state when error', async () => {
    server.use(http.get(GENERIC_JOB_URL, () => HttpResponse.error(), { once: true }));
    renderPanel();
    expect(
      await screen.findByText('Failed to fetch customization configuration')
    ).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});
