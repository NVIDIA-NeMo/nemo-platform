// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { extractDefaults } from '@nemo/common/src/components/form/ZodFormField/utils';
import { loraSchema } from '@nemo/common/src/components/TrainingParameterSlider/types';
import { getEntityReference } from '@nemo/common/src/namedEntity';
import { ModelEntity as CustomizationConfigOutput } from '@nemo/sdk/generated/platform/schema';
import { CustomizationJob, CustomizationJobRequest } from '@nemo/sdk/vendored/customizer/schema';
import { NEW_CUSTOMIZATION_FORM_HYP_DEFAULT_VALUES } from '@studio/components/NewCustomizationForm/constants';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { customizationJob1 } from '@studio/mocks/customizer/customization-jobs';
import { parentModel1, parentModel2 } from '@studio/mocks/customizer/parent-models';
import { dataset } from '@studio/mocks/datasets';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { server } from '@studio/mocks/node';
import { NewCustomizationRoute } from '@studio/routes/NewCustomizationRoute';
import {
  getWorkspaceCustomizationJobDetailsRoute,
  getNewCustomizationJobRoute,
} from '@studio/routes/utils';
import { LOCATION_DISPLAY_TEST_ID } from '@studio/tests/util/constants';
import { selectAutocompleteOption } from '@studio/tests/util/formUtils';
import { LocationDisplay } from '@studio/tests/util/LocationDisplay';
import { mockUseParams } from '@studio/tests/util/mockUseParams';
import { screen } from '@studio/tests/util/render';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

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

// TODO: Unskip when fixed - CustomizationDetails.tsx query is gated on distillation training type
describe.skip('Creating a new customization', () => {
  beforeEach(() => {
    mockUseParams({
      workspace: workspace1.workspace,
    });
  });
  describe('A user can create a customization', () => {
    const user = userEvent.setup();
    it('by selecting an existing dataset', async () => {
      // Mock the Customization create endpoint to capture the request body and return a happy result
      let customizationCreateRequestBody;
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

      // Select parent model
      await selectAutocompleteOption({
        user,
        autocompleteEl: await screen.findByRole('combobox', {
          name: 'Select a Customization Target',
        }),
        option: parentModel2.name!,
      });

      // Click the Select Dataset button, opening the dataset selection modal
      const selectDatasetButton = await screen.findByRole('button', { name: 'Select Dataset' });
      await user.click(selectDatasetButton);

      // Select the first row
      const selectRowCheckbox = await screen.findByRole('checkbox', {
        name: `Select dataset ${dataset.name}`,
      });
      await user.click(selectRowCheckbox);

      // Submit the dialog, selecting the dataset
      const dialogSubmitButton = screen.getByRole('button', { name: 'Add to Customization' });
      await user.click(dialogSubmitButton);

      // Enter output model name
      const outputModelInput = await screen.findByRole('textbox', { name: 'Output Model' });
      await user.clear(outputModelInput);
      await user.paste('test-customization-model');

      // Submit form
      const formSubmitButton = await screen.findByRole('button', { name: 'Start Fine-Tuning' });
      await user.click(formSubmitButton);

      // Assert the correct request was made
      // First training option (index 0) is auto-selected
      expect(customizationCreateRequestBody).toEqual({
        spec: {
          output_model: 'test-customization-model',
          dataset: getEntityReference(dataset),
          target: getEntityReference(parentModel2),
          hyperparameters: {
            ...NEW_CUSTOMIZATION_FORM_HYP_DEFAULT_VALUES,
            training_type: 'sft',
            finetuning_type: 'lora',
            lora: extractDefaults(loraSchema),
          },
        },
      });

      // Assert user was redirected to new customization route
      const location = (await screen.findByTestId(LOCATION_DISPLAY_TEST_ID)).textContent;
      expect(location).toEqual(
        getWorkspaceCustomizationJobDetailsRoute(workspace1.workspace, customizationJob1.name!)
      );
    });

    it('by creating a new dataset', async () => {
      // Mock the Customization create endpoint to capture the request body and return a happy result
      let customizationCreateRequestBody;
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

      // Select parent model
      await selectAutocompleteOption({
        user,
        autocompleteEl: await screen.findByRole('combobox', {
          name: 'Select a Customization Target',
        }),
        option: parentModel2.name!,
      });

      // Click the new dataset button, opening a modal
      const newDatasetButton = await screen.findByRole('button', { name: 'Create Dataset' });
      await user.click(newDatasetButton);

      // Fill out name and description
      const nameInput = await screen.findByRole('textbox', { name: 'Name' });
      await user.clear(nameInput);
      await user.paste('test-dataset-name');

      const descriptionInput = screen.getByRole('textbox', { name: 'Description' });
      await user.click(descriptionInput);
      await user.paste('Test dataset description');

      // Upload training file
      const trainingFileInput = screen.getByLabelText('Training File(s)');
      const trainingFile = new File(['test-file-contents'], 'training_file.jsonl', {
        type: 'application/json',
      });
      await user.upload(trainingFileInput, trainingFile);

      // Upload validation file
      const validationFileInput = screen.getByLabelText('Validation File(s)');
      const validationFile = new File(['test-file-contents'], 'validation_file.jsonl', {
        type: 'application/json',
      });
      await user.upload(validationFileInput, validationFile);

      // Submit the dialog, creating the dataset and using it
      const dialogSubmitButton = screen.getByRole('button', { name: 'Add to Customization' });
      await user.click(dialogSubmitButton);

      expect(await screen.findByText('Successfully created dataset!')).toBeInTheDocument();

      // Enter output model name
      const outputModelInput = await screen.findByRole('textbox', { name: 'Output Model' });
      await user.clear(outputModelInput);
      await user.paste('test-customization-model');

      // Submit form
      const formSubmitButton = await screen.findByRole('button', { name: 'Start Fine-Tuning' });
      await user.click(formSubmitButton);

      // Assert the correct request was made
      expect(customizationCreateRequestBody).toEqual({
        spec: {
          output_model: 'test-customization-model',
          dataset: getEntityReference(dataset),
          target: getEntityReference(parentModel2),
          hyperparameters: {
            ...NEW_CUSTOMIZATION_FORM_HYP_DEFAULT_VALUES,
            training_type: 'sft',
            finetuning_type: 'lora',
            lora: extractDefaults(loraSchema),
          },
        },
      });

      // Assert user was redirected to new customization route
      const location = (await screen.findByTestId(LOCATION_DISPLAY_TEST_ID)).textContent;
      expect(location).toEqual(
        getWorkspaceCustomizationJobDetailsRoute(workspace1.workspace, customizationJob1.name!)
      );
    });
  });

  describe('A user cannot create a customization', () => {
    it('if they have not selected a dataset', async () => {
      const user = userEvent.setup();
      renderRoute();

      // Select parent model
      await selectAutocompleteOption({
        user,
        autocompleteEl: await screen.findByRole('combobox', {
          name: 'Select a Pre-built Configuration',
        }),
        option: parentModel2.name!,
      });

      // Training option is automatically selected when model is chosen

      // Submit button is always enabled; validation happens on submit attempt
      const formSubmitButton = await screen.findByRole('button', { name: 'Start Fine-Tuning' });
      expect(formSubmitButton).not.toBeDisabled();

      // Do NOT select a dataset - verify the Select Dataset and New Dataset buttons are present
      const selectDatasetButton = await screen.findByRole('button', { name: 'Select Dataset' });
      const newDatasetButton = await screen.findByRole('button', { name: 'Create Dataset' });
      expect(selectDatasetButton).toBeInTheDocument();
      expect(newDatasetButton).toBeInTheDocument();
    });

    it('if the selected dataset has no training file', async () => {
      const user = userEvent.setup();
      // Mock the files query to return only a validation file (no training file)
      server.use(
        http.get(
          `${PLATFORM_BASE_URL}/v1/hf/api/datasets/${getEntityReference(dataset)}/tree/main`,
          () => {
            return HttpResponse.json([
              {
                path: 'validation/validation_file.jsonl',
                type: 'file',
                size: 100,
              },
            ]);
          }
        )
      );

      renderRoute();

      // Select parent model
      await selectAutocompleteOption({
        user,
        autocompleteEl: await screen.findByRole('combobox', {
          name: 'Select a Pre-built Configuration',
        }),
        option: parentModel2.name!,
      });

      // Training option is automatically selected when model is chosen

      // Click the Select Dataset button, opening the dataset selection modal
      const selectDatasetButton = await screen.findByRole('button', { name: 'Select Dataset' });
      await user.click(selectDatasetButton);

      // Select the first row (our mocked dataset with only validation file)
      const selectRowCheckbox = await screen.findByRole('checkbox', {
        name: `Select dataset ${dataset.name}`,
      });
      await user.click(selectRowCheckbox);

      // Submit the dialog, selecting the dataset
      const dialogSubmitButton = screen.getByRole('button', { name: 'Add to Customization' });
      await user.click(dialogSubmitButton);

      // Verify the validation error message appears for missing training file
      const trainingFileError = await screen.findByText('No Training Data Found');
      expect(trainingFileError).toBeInTheDocument();

      // Submit button is still enabled, but form validation will prevent actual submission
      const formSubmitButton = await screen.findByRole('button', { name: 'Start Fine-Tuning' });
      expect(formSubmitButton).not.toBeDisabled();
    });

    it('if the selected dataset has no validation file', async () => {
      const user = userEvent.setup();
      // Mock the files query to return only a training file (no validation file)
      server.use(
        http.get(
          `${PLATFORM_BASE_URL}/v1/hf/api/datasets/${getEntityReference(dataset)}/tree/main`,
          () => {
            return HttpResponse.json([
              {
                path: 'training/training_file.jsonl',
                type: 'file',
                size: 100,
              },
            ]);
          }
        )
      );

      renderRoute();

      // Select parent model
      await selectAutocompleteOption({
        user,
        autocompleteEl: await screen.findByRole('combobox', {
          name: 'Select a Pre-built Configuration',
        }),
        option: parentModel2.name!,
      });

      // Training option is automatically selected when model is chosen

      // Click the Select Dataset button, opening the dataset selection modal
      const selectDatasetButton = await screen.findByRole('button', { name: 'Select Dataset' });
      await user.click(selectDatasetButton);

      // Select the first row (our mocked dataset with only training file)
      const selectRowCheckbox = await screen.findByRole('checkbox', {
        name: `Select dataset ${dataset.name}`,
      });
      await user.click(selectRowCheckbox);

      // Submit the dialog, selecting the dataset
      const dialogSubmitButton = screen.getByRole('button', { name: 'Add to Customization' });
      await user.click(dialogSubmitButton);

      // Verify the validation error message appears for missing validation file
      const validationFileError = await screen.findByText('No Validation Data Found');
      expect(validationFileError).toBeInTheDocument();

      // Submit button is still enabled, but form validation will prevent actual submission
      const formSubmitButton = await screen.findByRole('button', { name: 'Start Fine-Tuning' });
      expect(formSubmitButton).not.toBeDisabled();
    });
  });

  describe('Hyperparameter subsections display correctly based on training options', () => {
    it('Shows DPO Parameters section when training_type is "dpo"', async () => {
      const user = userEvent.setup();
      // Mock a parent model with DPO training type
      const dpoModel: CustomizationConfigOutput = {
        ...parentModel1,
        name: 'dpo-model-config',
      };

      // Mock the parent models endpoint to return our DPO model
      server.use(
        http.get(
          `${PLATFORM_BASE_URL}/apis/customization/v2/workspaces/${workspace1.workspace}/targets`,
          () => {
            return HttpResponse.json({ data: [dpoModel] });
          }
        )
      );

      renderRoute();

      // Select parent model
      await selectAutocompleteOption({
        user,
        autocompleteEl: await screen.findByRole('combobox', {
          name: 'Select a Pre-built Configuration',
        }),
        option: dpoModel.name!,
      });

      // Expand the hyperparameters accordion
      const hyperparametersAccordion = await screen.findByText('Hyperparameters (Advanced)');
      await user.click(hyperparametersAccordion);

      // Verify DPO Parameters section is visible
      const dpoParametersHeading = await screen.findByText('DPO Parameters');
      expect(dpoParametersHeading).toBeInTheDocument();
    });

    it('Shows LoRA Parameters section when finetuning_type is "lora"', async () => {
      const user = userEvent.setup();
      // Mock a parent model with LoRA finetuning type
      const loraModel: CustomizationConfigOutput = {
        ...parentModel1,
        name: 'lora-model-config',
      };

      // Mock the parent models endpoint to return our LoRA model
      server.use(
        http.get(
          `${PLATFORM_BASE_URL}/apis/customization/v2/workspaces/${workspace1.workspace}/targets`,
          () => {
            return HttpResponse.json({ data: [loraModel] });
          }
        )
      );

      renderRoute();

      // Select parent model
      await selectAutocompleteOption({
        user,
        autocompleteEl: await screen.findByRole('combobox', {
          name: 'Select a Pre-built Configuration',
        }),
        option: loraModel.name!,
      });

      // Expand the hyperparameters accordion
      const hyperparametersAccordion = await screen.findByText('Hyperparameters (Advanced)');
      await user.click(hyperparametersAccordion);

      // Verify LoRA Parameters section is visible
      const loraParametersHeading = await screen.findByText('LoRA Parameters');
      expect(loraParametersHeading).toBeInTheDocument();
    });

    it('Shows both SFT and LoRA Parameters sections when both apply', async () => {
      const user = userEvent.setup();
      // Mock a parent model with both SFT training type and LoRA finetuning type
      const sftLoraModel: CustomizationConfigOutput = {
        ...parentModel1,
        name: 'sft-lora-model-config',
      };

      // Mock the parent models endpoint to return our SFT+LoRA model
      server.use(
        http.get(
          `${PLATFORM_BASE_URL}/apis/customization/v2/workspaces/${workspace1.workspace}/targets`,
          () => {
            return HttpResponse.json({ data: [sftLoraModel] });
          }
        )
      );

      renderRoute();

      // Select parent model
      await selectAutocompleteOption({
        user,
        autocompleteEl: await screen.findByRole('combobox', {
          name: 'Select a Pre-built Configuration',
        }),
        option: sftLoraModel.name!,
      });

      // Expand the hyperparameters accordion
      const hyperparametersAccordion = await screen.findByText('Hyperparameters (Advanced)');
      await user.click(hyperparametersAccordion);

      // Verify both SFT and LoRA Parameters sections are visible
      const sftParametersHeading = await screen.findByText('SFT Parameters');
      const loraParametersHeading = await screen.findByText('LoRA Parameters');
      expect(sftParametersHeading).toBeInTheDocument();
      expect(loraParametersHeading).toBeInTheDocument();
    });
  });
});
