// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getEntityReference } from '@nemo/common/src/namedEntity';
import type { ModelEntitysPage } from '@nemo/sdk/generated/platform/schema';
import type {
  CustomizationJob,
  CustomizationJobRequest,
} from '@nemo/sdk/vendored/customizer/schema';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { customizationJob1 } from '@studio/mocks/customizer/customization-jobs';
import { parentModel2 } from '@studio/mocks/customizer/parent-models';
import { dataset } from '@studio/mocks/datasets';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { server } from '@studio/mocks/node';
import { NewCustomizationRoute } from '@studio/routes/NewCustomizationRoute';
import {
  getWorkspaceCustomizationJobDetailsRoute,
  getNewCustomizationJobRoute,
} from '@studio/routes/utils';
import { LOCATION_DISPLAY_TEST_ID } from '@studio/tests/util/constants';
import { LocationDisplay } from '@studio/tests/util/LocationDisplay';
import { mockUseParams } from '@studio/tests/util/mockUseParams';
import { screen } from '@studio/tests/util/render';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

// Extend the mock parent model with a fileset so ModelSelectionSection shows it
// (the component filters out models without a fileset)
const parentModel2WithFileset = {
  ...parentModel2,
  fileset: `${parentModel2.workspace}/${parentModel2.name}-fileset`,
};

const renderRoute = () => {
  const routes = [
    {
      path: ROUTES.workspace.newCustomizationJob,
      element: <NewCustomizationRoute />,
    },
    { path: ROUTES.workspace.customizationJobDetails, element: <LocationDisplay /> },
  ];

  const router = createMemoryRouter(routes, {
    initialEntries: [getNewCustomizationJobRoute(workspace1.workspace)],
  });

  return render(
    <TestProviders>
      <RouterProvider router={router} />
    </TestProviders>
  );
};

describe('Creating a new customization', () => {
  beforeEach(() => {
    mockUseParams({
      workspace: workspace1.workspace,
    });

    // Override the default models handler to return a model with a fileset.
    // ModelSelectionSection filters to only show models that have a fileset field.
    server.use(
      http.get<never, never, ModelEntitysPage>(
        `${PLATFORM_BASE_URL}/apis/models/v2/workspaces/${workspace1.workspace}/models`,
        () => HttpResponse.json({ data: [parentModel2WithFileset] })
      )
    );
  });

  describe('A user can create a customization', () => {
    it('by selecting an existing dataset', async () => {
      const user = userEvent.setup();

      let customizationCreateRequestBody: CustomizationJobRequest | undefined;
      server.use(
        http.post<never, CustomizationJobRequest, CustomizationJob>(
          `${PLATFORM_BASE_URL}/apis/customization/v2/workspaces/${workspace1.workspace}/jobs`,
          async ({ request }) => {
            customizationCreateRequestBody = await request.json();
            return HttpResponse.json(customizationJob1);
          },
          { once: true }
        )
      );

      renderRoute();

      // Select base model — wait for the trigger to be enabled (models API must resolve first)
      const modelSelectTrigger = await screen.findByTestId('model-select-v2-trigger');
      await waitFor(() => expect(modelSelectTrigger).not.toBeDisabled());
      await user.click(modelSelectTrigger);

      // Find the model dropdown item by name and click it
      const modelItems = await screen.findAllByTestId('model-dropdown-item');
      const targetModelItem = modelItems.find(
        (item) => within(item).queryByText(parentModel2.name!) !== null
      );
      expect(targetModelItem).toBeDefined();
      await user.click(targetModelItem!);

      // Select dataset from the dropdown
      const datasetSelect = await screen.findByRole('combobox', { name: /dataset/i });
      await user.click(datasetSelect);
      const datasetOption = await screen.findByRole('option', { name: dataset.name! });
      await user.click(datasetOption);

      // Wait for file list to appear and full per-file validation to complete.
      // 'File Validation' only renders after useCustomizationDatasetValidation
      // finishes (isPending → false), which happens after file discovery resolves.
      // By that point the useEffect in NewCustomizationForm has already set
      // trainingFileExists = true, so the form is valid when we click submit.
      await screen.findByText('training/training_file.jsonl');
      await screen.findByText('File Validation');

      // Set output model name
      const outputModelInput = await screen.findByRole('textbox', { name: 'Output Model Name' });
      await user.clear(outputModelInput);
      await user.type(outputModelInput, 'test-customization-model');

      // Submit form
      const formSubmitButton = await screen.findByRole('button', { name: 'Start Fine-Tuning' });
      await user.click(formSubmitButton);

      // Assert the correct request was made
      await waitFor(() => {
        expect(customizationCreateRequestBody).toMatchObject({
          name: 'test-customization-model',
          spec: {
            model: getEntityReference(parentModel2),
            dataset: `fileset://${dataset.workspace}/${dataset.name}`,
            training: expect.objectContaining({ type: 'sft' }),
            output: expect.objectContaining({ name: 'test-customization-model' }),
          },
        });
      });

      // Assert user was redirected to the customization job details route
      const location = (await screen.findByTestId(LOCATION_DISPLAY_TEST_ID)).textContent;
      expect(location).toEqual(
        getWorkspaceCustomizationJobDetailsRoute(workspace1.workspace, customizationJob1.name!)
      );
    });
  });

  describe('Hyperparameter subsections display correctly based on training type', () => {
    it('Shows DPO Parameters section when training type is "dpo"', async () => {
      const user = userEvent.setup();
      renderRoute();

      // Click the DPO radio card to switch training type
      const dpoRadio = await screen.findByRole('radio', { name: 'DPO' });
      await user.click(dpoRadio);

      // DPO Parameters section should now be visible
      const dpoParametersHeading = await screen.findByText('DPO Parameters');
      expect(dpoParametersHeading).toBeInTheDocument();
    });

    it('Shows LoRA Parameters section when training type is "sft"', async () => {
      renderRoute();

      // SFT with LoRA is the default training configuration — the LoRA rank
      // selector should be visible without any user interaction
      const loraRankSelector = await screen.findByTestId('lora-rank');
      expect(loraRankSelector).toBeInTheDocument();
    });
  });
});
