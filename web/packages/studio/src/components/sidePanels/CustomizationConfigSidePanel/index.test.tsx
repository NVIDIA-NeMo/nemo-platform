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
import {
  getBaseModel,
  getCustomizationConfigurationName,
  getFormattedTrainingType,
} from '@studio/util/customizations';
import { render, screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

describe('CustomizationConfigSidePanel', () => {
  it('should render loading state when loading', async () => {
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
    render(
      <TestProviders>
        <RouterProvider router={router} />
      </TestProviders>
    );
    expect(await screen.findByText('Loading...')).toBeInTheDocument();
  });

  it('should render customization configuration details', async () => {
    // Use job with LoRA training for full assertions
    const fullCustomizationJob = customizationJob2;
    server.use(
      http.get(
        `${PLATFORM_BASE_URL}/apis/customization/v2/workspaces/${workspace1.workspace}/jobs/:job_id`,
        () => HttpResponse.json(fullCustomizationJob),
        { once: true }
      )
    );
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
    render(
      <TestProviders>
        <RouterProvider router={router} />
      </TestProviders>
    );
    expect(screen.getByText('Customization Configuration')).toBeInTheDocument();
    expect(await screen.findByText('Name')).toBeInTheDocument();
    expect(
      screen.getAllByText(getCustomizationConfigurationName(fullCustomizationJob.spec.model) || '-')
        .length
    ).toBeGreaterThan(0);
    expect(screen.getByText('Configuration Snapshot')).toBeInTheDocument();
    expect(screen.getByText('Base Model')).toBeInTheDocument();
    expect(screen.getAllByText(getBaseModel(fullCustomizationJob)).length).toBeGreaterThan(0);
    expect(screen.getByText('Training Type')).toBeInTheDocument();
    const training = fullCustomizationJob.spec.training;
    const trainingType = training && 'type' in training ? training.type : undefined;
    expect(screen.getByText(getFormattedTrainingType(trainingType))).toBeInTheDocument();
    expect(screen.getByText('Finetuning Type')).toBeInTheDocument();
    expect(
      screen.getByText(
        getFormattedTrainingType(
          training && 'peft' in training && training.peft ? 'lora' : 'all_weights'
        )
      )
    ).toBeInTheDocument();
    expect(screen.getByText('Training Options')).toBeInTheDocument();
    expect(screen.getByText('Hyperparameters')).toBeInTheDocument();
    expect(screen.getByText('Warmup Steps')).toBeInTheDocument();
    const specTraining = fullCustomizationJob.spec.training;
    const warmup =
      specTraining && 'warmup_steps' in specTraining ? specTraining.warmup_steps : undefined;
    const seed = specTraining && 'seed' in specTraining ? specTraining.seed : undefined;
    const maxSteps =
      specTraining && 'max_steps' in specTraining ? specTraining.max_steps : undefined;
    const optimizer =
      specTraining && 'optimizer' in specTraining ? specTraining.optimizer : undefined;
    const adamBeta1 =
      specTraining && 'adam_beta1' in specTraining ? specTraining.adam_beta1 : undefined;
    const adamBeta2 =
      specTraining && 'adam_beta2' in specTraining ? specTraining.adam_beta2 : undefined;
    const batchSize =
      specTraining && 'batch_size' in specTraining ? specTraining.batch_size : undefined;
    const epochs = specTraining && 'epochs' in specTraining ? specTraining.epochs : undefined;
    const learningRate =
      specTraining && 'learning_rate' in specTraining ? specTraining.learning_rate : undefined;
    const logEvery =
      specTraining && 'log_every_n_steps' in specTraining
        ? specTraining.log_every_n_steps
        : undefined;
    const loraTraining = fullCustomizationJob.spec.training;
    const peft = loraTraining && 'peft' in loraTraining ? loraTraining.peft : undefined;
    expect(screen.getByText(String(warmup ?? '-'))).toBeInTheDocument();
    expect(screen.getByText('Seed')).toBeInTheDocument();
    expect(screen.getByText(String(seed ?? '-'))).toBeInTheDocument();
    expect(screen.getByText('Max Steps')).toBeInTheDocument();
    expect(screen.getByText(String(maxSteps ?? '-'))).toBeInTheDocument();
    expect(screen.getByText('Optimizer')).toBeInTheDocument();
    expect(screen.getByText(String(optimizer ?? '-'))).toBeInTheDocument();
    expect(screen.getByText('Adam Beta 1')).toBeInTheDocument();
    expect(screen.getByText(String(adamBeta1 ?? '-'))).toBeInTheDocument();
    expect(screen.getByText('Adam Beta 2')).toBeInTheDocument();
    expect(screen.getByText(String(adamBeta2 ?? '-'))).toBeInTheDocument();
    expect(screen.getByText('Batch Size')).toBeInTheDocument();
    expect(screen.getByText(String(batchSize ?? '-'))).toBeInTheDocument();
    expect(screen.getByText('Epochs')).toBeInTheDocument();
    expect(screen.getByText(String(epochs ?? '-'))).toBeInTheDocument();
    expect(screen.getByText('Learning Rate')).toBeInTheDocument();
    expect(screen.getByText(String(learningRate ?? '-'))).toBeInTheDocument();
    expect(screen.getByText('Log Every N Steps')).toBeInTheDocument();
    expect(screen.getByText(String(logEvery ?? '-'))).toBeInTheDocument();
    expect(screen.getByText('LoRA / Rank')).toBeInTheDocument();
    expect(screen.getByText(String(peft?.rank ?? '-'))).toBeInTheDocument();
    expect(screen.getByText('LoRA / Alpha')).toBeInTheDocument();
    expect(screen.getByText(String(peft?.alpha ?? '-'))).toBeInTheDocument();
    expect(screen.getByText('LoRA / Target Modules')).toBeInTheDocument();
    expect(screen.getByText(peft?.target_modules?.join(', ') ?? '-')).toBeInTheDocument();
  });

  it('should render error state when error', async () => {
    server.use(
      http.get(
        `${PLATFORM_BASE_URL}/apis/customization/v2/workspaces/${workspace1.workspace}/jobs/:job_id`,
        () => HttpResponse.error(),
        { once: true }
      )
    );
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
    render(
      <TestProviders>
        <RouterProvider router={router} />
      </TestProviders>
    );
    expect(
      await screen.findByText('Failed to fetch customization configuration')
    ).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});
