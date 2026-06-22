// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  MAX_TOKENS_DEFAULT,
  TEMPERATURE_DEFAULT,
} from '@nemo/common/src/constants/inferenceParameters';
import { DEFAULT_PROMPT_TEMPLATE } from '@nemo/common/src/models/constants';
import { compileSystemPrompt } from '@nemo/common/src/models/utils';
import { useFilesListFilesets as useListDatasets } from '@nemo/sdk/generated/platform/api';
import { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { DEFAULT_NAMESPACE } from '@studio/constants/constants';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTES, ROUTE_PARAMS } from '@studio/constants/routes';
import { dataset1 } from '@studio/mocks/entity-store/datasets';
import { entityStoreBaseModel1 } from '@studio/mocks/entity-store/models';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { server } from '@studio/mocks/node';
import { CustomizationJobListRoute } from '@studio/routes/CustomizationJobListRoute';
import { PromptTuningFormRoute } from '@studio/routes/PromptTuningFormRoute';
import { getWorkspaceCustomizationJobListRoute } from '@studio/routes/utils';
import { mockUseParams } from '@studio/tests/util/mockUseParams';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

const workspace = workspace1;
const baseModel = entityStoreBaseModel1;

// Mock the platform API to override useFilesListFilesets
const useListFilesetsMock = vi.hoisted(() => vi.fn());
vi.mock('@nemo/sdk/generated/platform/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@nemo/sdk/generated/platform/api')>();
  return {
    ...actual,
    useFilesListFilesets: useListFilesetsMock,
  };
});

const renderRoute = () => {
  const router = createMemoryRouter(
    [
      { path: ROUTES.workspace.customizationJobList, element: <CustomizationJobListRoute /> },
      { path: ROUTES.workspace.promptTuningForm, element: <PromptTuningFormRoute /> },
    ],
    {
      initialEntries: [getWorkspaceCustomizationJobListRoute(workspace.workspace)],
    }
  );
  return render(
    <TestProviders>
      <RouterProvider router={router} />
    </TestProviders>
  );
};

describe('Create a model', () => {
  const user = userEvent.setup();

  beforeEach(() => {
    vi.clearAllMocks();

    mockUseParams({
      [ROUTE_PARAMS.workspace]: workspace.workspace,
    });

    // Mock useListDatasets to return dataset1
    useListFilesetsMock.mockReturnValue({
      data: { data: [dataset1] },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useListDatasets>);

    // Mock the SDK hook for getting a specific model
    server.use(
      http.get<never, never, ModelEntity>(
        `${PLATFORM_BASE_URL}/apis/models/v2/workspaces/${baseModel.workspace}/models/${baseModel.name}`,
        async () => HttpResponse.json(baseModel)
      )
    );

    // Override the models list endpoint to return the base model for any workspace
    // This is needed because base models may be in a different workspace (e.g., 'meta')
    // than the current workspace being browsed (e.g., 'default')
    server.use(
      http.get(`${PLATFORM_BASE_URL}/apis/models/v2/workspaces/:workspace/models`, () =>
        HttpResponse.json({
          data: [baseModel],
          pagination: {
            page: 1,
            page_size: 50,
            total_pages: 1,
            total_results: 1,
          },
        })
      )
    );

    // Mock the deployments endpoint to return a READY deployment for the base model
    server.use(
      http.get(`${PLATFORM_BASE_URL}/apis/models/v2/workspaces/:workspace/deployments`, () =>
        HttpResponse.json({
          data: [
            {
              name: baseModel.name,
              workspace: baseModel.workspace,
              entity_version: 1,
              config: 'default-config',
              config_version: 1,
              status: 'READY',
              status_message: '',
              created_at: baseModel.created_at,
              updated_at: baseModel.updated_at,
            },
          ],
          pagination: {
            page: 1,
            page_size: 1000,
            total_pages: 1,
            total_results: 1,
          },
        })
      )
    );
  });
  it('A user can create a model successfully using defaults', async () => {
    const sampleModelInput = {
      name: 'test-model-name',
      base_model: baseModel.name,
    };

    renderRoute();

    // Click the Create New Model button
    const newModelButton = await screen.findByRole('button', { name: 'Customize a Model' });
    await user.click(newModelButton);

    // Click the Prompt Tuned option
    const promptTunedOption = screen.getByRole('radio', { name: 'Prompt Tuned ICLs' });
    await user.click(promptTunedOption);
    await user.click(screen.getByRole('button', { name: 'Continue' }));

    // Select model
    const modelSelect = screen.getByTestId('model-select-v2-trigger');
    await user.click(modelSelect);
    const options = await screen.findAllByTestId('model-dropdown-item');
    await user.click(options[0]);

    // Click Save Model
    const saveButton = screen.getByRole('button', { name: 'Save Model' });
    await user.click(saveButton);

    // Enter name
    const modelNameInput = screen.getByRole('textbox', { name: 'Model Name' });
    await user.clear(modelNameInput);
    await user.paste(sampleModelInput.name);

    // Mock the Model create endpoint to capture the request body and return a happy result
    let modelCreateRequestBody;
    let modelCreateResponseBody;
    server.use(
      http.post(
        `${PLATFORM_BASE_URL}/apis/models/v2/workspaces/${DEFAULT_NAMESPACE}/models`,
        async ({ request }) => {
          modelCreateRequestBody = (await request.json()) as ModelEntity;
          modelCreateResponseBody = {
            ...modelCreateRequestBody,
            ...sampleModelInput,
            workspace: DEFAULT_NAMESPACE,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          };
          return HttpResponse.json(modelCreateResponseBody);
        }
      )
    );

    // Load that newly created model fresh as its own object
    server.use(
      http.get<never, never, ModelEntity>(
        `${PLATFORM_BASE_URL}/apis/models/v2/workspaces/${DEFAULT_NAMESPACE}/models/${sampleModelInput.name}`,
        async () =>
          HttpResponse.json({
            ...sampleModelInput,
            id: 'model-created-1',
            workspace: DEFAULT_NAMESPACE,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          })
      )
    );

    // Confirm
    const confirmButton = screen.getByRole('button', { name: 'Save' });
    await user.click(confirmButton);

    // Assert the correct request was made
    expect(modelCreateRequestBody).toMatchObject({
      ...sampleModelInput,
      prompt: {
        icl_few_shot_examples: '',
        system_prompt: compileSystemPrompt({
          systemPromptTemplate: DEFAULT_PROMPT_TEMPLATE,
          iclFewShotExamples: '',
        }).prompt,
      },
      custom_fields: {
        system_prompt_template: compileSystemPrompt({
          systemPromptTemplate: DEFAULT_PROMPT_TEMPLATE,
          iclFewShotExamples: '',
        }).promptTemplate,
        workspace: DEFAULT_NAMESPACE,
        inference_params: {
          temperature: TEMPERATURE_DEFAULT,
          max_tokens: MAX_TOKENS_DEFAULT,
        },
      },
    });
  });

  it('A user can create a model successfully inputting all fields', async () => {
    const sampleModelInput = {
      name: 'test-model-name',
      description: 'Test Model Description',
      base_model: baseModel.name,
    };

    const expectedTemperature = 1.9;
    const expectedMaxTokens = 2345;
    // TODO: Change back to 'Test Model Template\n\n{{icl_few_shot_examples}}' once toolCallingEnabled is enabled by default
    const expectedSystemPromptTemplate = 'Test Model Template';

    renderRoute();

    // Click the Create New Model button
    const newModelButton = await screen.findByRole('button', { name: 'Customize a Model' });
    await user.click(newModelButton);

    // Click the Prompt Tuned option
    const promptTunedOption = screen.getByRole('radio', { name: 'Prompt Tuned ICLs' });
    await user.click(promptTunedOption);
    await user.click(screen.getByRole('button', { name: 'Continue' }));

    // Select model
    const modelSelect = screen.getByTestId('model-select-v2-trigger');
    await user.click(modelSelect);
    const options = await screen.findAllByTestId('model-dropdown-item');
    await user.click(options[0]);

    // Enter system prompt template
    const templateInput = screen.getByRole('textbox', { name: 'System Instructions' });
    await user.click(templateInput);
    await user.paste('Test Model Template');

    // TODO: Uncomment once toolCallingEnabled feature flag is enabled by default
    // // Open ICL Modal
    // const iclExamplesAccordion = screen.getByText('Learning Examples');
    // await user.click(iclExamplesAccordion);
    // const iclButton = screen.getByRole('button', { name: 'Import Examples' });
    // await user.click(iclButton);
    //
    // // Select fileset
    // const iclDatasetSelect = screen.getByRole('combobox', { name: 'Fileset' });
    // await user.click(iclDatasetSelect);
    // const iclDatasetOptions = screen.getAllByRole('option');
    // await user.click(iclDatasetOptions[0]);
    // // Wait for files to load and select first file
    // await waitFor(() => {
    //   const checkboxes = screen.getAllByRole('checkbox');
    //   expect(checkboxes.length).toBeGreaterThan(0);
    // });
    // const fileCheckboxes = screen.getAllByRole('checkbox');
    // await user.click(fileCheckboxes[0]);
    // const confirmIclButton = screen.getByRole('button', { name: 'Confirm' });
    // await user.click(confirmIclButton);
    // await waitFor(() => expect(confirmIclButton).not.toBeInTheDocument());

    // Enter hyperparams
    const accordionTitle = screen.getByText('Hyperparameters');
    await user.click(accordionTitle);
    const temperatureInput = screen.getByLabelText('temperature-slider_text_input');
    fireEvent.change(temperatureInput, { target: { value: expectedTemperature.toString() } });
    const maxTokenInput = screen.getByLabelText('max_tokens-slider_text_input');
    fireEvent.change(maxTokenInput, { target: { value: expectedMaxTokens.toString() } });

    // Click Save Model
    const saveButton = screen.getByRole('button', { name: 'Save Model' });
    await user.click(saveButton);

    // Enter name
    const modelNameInput = screen.getByRole('textbox', { name: 'Model Name' });
    await user.clear(modelNameInput);
    await user.paste(sampleModelInput.name);

    // Enter description
    const descriptionInput = screen.getByRole('textbox', { name: 'Description' });
    await user.click(descriptionInput);
    await user.paste(sampleModelInput.description);

    // Mock the Model create endpoint to capture the request body and return a happy result
    let modelCreateRequestBody;
    let modelCreateResponseBody;
    server.use(
      http.post<never, never, ModelEntity>(
        `${PLATFORM_BASE_URL}/apis/models/v2/workspaces/${DEFAULT_NAMESPACE}/models`,
        async ({ request }) => {
          modelCreateRequestBody = (await request.json()) as ModelEntity;
          modelCreateResponseBody = {
            ...modelCreateRequestBody,
            ...sampleModelInput,
            workspace: DEFAULT_NAMESPACE,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          };
          return HttpResponse.json(modelCreateResponseBody);
        }
      )
    );

    // Load that newly created model fresh as its own object
    server.use(
      http.get<never, never, ModelEntity>(
        `${PLATFORM_BASE_URL}/apis/models/v2/workspaces/${DEFAULT_NAMESPACE}/models/${sampleModelInput.name}`,
        async () =>
          HttpResponse.json({
            ...sampleModelInput,
            id: 'model-created-2',
            workspace: DEFAULT_NAMESPACE,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          })
      )
    );

    // Confirm
    const confirmButton = screen.getByRole('button', { name: 'Save' });
    await user.click(confirmButton);

    // Assert the correct request was made
    expect(modelCreateRequestBody).toMatchObject({
      ...sampleModelInput,
      prompt: {
        system_prompt: expect.stringContaining('Test Model Template'),
        icl_few_shot_examples: expect.any(String),
      },
      custom_fields: {
        system_prompt_template: expectedSystemPromptTemplate,
        workspace: DEFAULT_NAMESPACE,
        inference_params: {
          temperature: expectedTemperature,
          max_tokens: expectedMaxTokens,
        },
      },
    });
  });
});
