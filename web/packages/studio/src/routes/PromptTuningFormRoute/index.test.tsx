// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { suppressConsoleError } from '@nemo/testing/utils/suppress-console';
import { TOOL_JSON_EXAMPLE } from '@studio/components/PromptTuningForm/ToolsSection/constants';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { entityStoreCustomizedModel1 } from '@studio/mocks/entity-store/models';
import { testWorkspace } from '@studio/mocks/entity-store/projects';
import { server } from '@studio/mocks/node';
import { PromptTuningFormRoute } from '@studio/routes/PromptTuningFormRoute';
import { getPromptTuningFormRoute } from '@studio/routes/utils';
import { LG_SELECTOR_TIMEOUT, XL_SELECTOR_TIMEOUT } from '@studio/tests/util/constants';
import { mockFeatureFlags } from '@studio/tests/util/mockFeatureFlags';
import { mockUseModelChatAvailability } from '@studio/tests/util/mockUseModelChatAvailability';
import { mockUseParams } from '@studio/tests/util/mockUseParams';
import { waitFor } from '@studio/tests/util/render';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

// Mock useChatCompletion to capture the request parameters
const mockMutateAsync = vi.fn();
vi.mock('@nemo/common/src/hooks/useChatCompletion', () => ({
  useChatCompletion: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
    isError: false,
    error: null,
  }),
}));

// mockUseModelChatAvailability import registers the vi.mock; call it to override defaults per-test.

// Helper to create mock stream - called fresh in beforeEach to survive vi.restoreAllMocks()
const createMockStream = () => ({
  [Symbol.asyncIterator]: async function* () {
    yield { choices: [{ delta: { content: 'Hello' } }] };
  },
  controller: { abort: vi.fn() },
});

const LARGE_SYSTEM_PROMPT = 'A'.repeat(11000);

const renderRoute = () => {
  const routes = [
    {
      path: getPromptTuningFormRoute(testWorkspace),
      element: <PromptTuningFormRoute />,
    },
  ];
  return render(
    <TestProviders>
      <RouterProvider
        router={createMemoryRouter(routes, {
          initialEntries: [getPromptTuningFormRoute(testWorkspace)],
        })}
      />
    </TestProviders>
  );
};

describe('PromptTuningFormRoute', () => {
  beforeEach(() => {
    // Reset mock implementation before each test (survives vi.restoreAllMocks())
    mockMutateAsync.mockImplementation(() => Promise.resolve(createMockStream()));

    mockUseParams({
      [ROUTE_PARAMS.workspace]: testWorkspace,
    });
  });

  it('renders', async () => {
    renderRoute();
    await waitFor(() => expect(screen.queryByTestId('spinner')).not.toBeInTheDocument(), {
      timeout: LG_SELECTOR_TIMEOUT,
    });
    await screen.findByText(`Model Parameters`);
    expect(screen.getByText(`System Instructions`)).toBeInTheDocument();
  });

  it('hides Learning Examples and Tools when toolCallingEnabled is false', async () => {
    renderRoute();
    await waitFor(() => expect(screen.queryByTestId('spinner')).not.toBeInTheDocument(), {
      timeout: LG_SELECTOR_TIMEOUT,
    });
    await screen.findByText(`Model Parameters`);
    expect(screen.queryByText(`Learning Examples`)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Tools' })).not.toBeInTheDocument();
  });

  it('should transform spaces to dashes in model name field as user types', async () => {
    const user = userEvent.setup();
    renderRoute();

    // Select model
    const modelSelect = screen.getByTestId('model-select-v2-trigger');
    await waitFor(() => expect(modelSelect).toBeEnabled());
    await user.click(modelSelect);
    const options = await screen.findAllByTestId('model-dropdown-item');
    await user.click(options[0]);

    // Click Save Model
    const saveButton = screen.getByRole('button', { name: 'Save Model' });
    await user.click(saveButton);

    // Enter name
    const modelNameInput = screen.getByRole('textbox', { name: 'Model Name' });
    await user.clear(modelNameInput); // TODO: This shouldn't be necessary but the first test's state is leaking into this one
    await user.type(modelNameInput, 'my model name');

    // Verify that spaces are automatically transformed to dashes
    expect(modelNameInput).toHaveValue('my-model-name');
  });

  describe('with toolCallingEnabled', () => {
    beforeEach(() => {
      mockFeatureFlags({ toolCallingEnabled: true });
    });

    it('renders Learning Examples when toolCallingEnabled is true', async () => {
      renderRoute();
      await waitFor(() => expect(screen.queryByTestId('spinner')).not.toBeInTheDocument(), {
        timeout: LG_SELECTOR_TIMEOUT,
      });
      await screen.findByText(`Model Parameters`);
      expect(screen.getByText(`Learning Examples`)).toBeInTheDocument();
    });

    it('should support tools for inference', async () => {
      const user = userEvent.setup();
      renderRoute();
      await waitFor(() => expect(screen.queryByTestId('spinner')).not.toBeInTheDocument());

      // Select model
      const modelSelect = screen.getByTestId('model-select-v2-trigger');
      await waitFor(() => expect(modelSelect).toBeEnabled());
      await user.click(modelSelect);

      const options = await screen.findAllByTestId('model-dropdown-item');
      await user.click(options[0]);

      // Open tools accordion and add a tool
      // KUI Accordion uses native <summary> trigger which lacks role="button".
      const toolsAccordion = screen.getByText('Tools');
      await user.click(toolsAccordion);
      const addToolButton = screen.getByRole('button', { name: 'Add Tools' });
      await user.click(addToolButton);

      // Submit the form (the default tool example "get_current_weather" is already populated)
      const addToolSubmitButton = screen.getByRole('button', { name: 'Save' });
      await user.click(addToolSubmitButton);

      // Verify that the tool appears in the list
      expect(
        await screen.findByText('get_current_weather', undefined, { timeout: LG_SELECTOR_TIMEOUT })
      ).toBeInTheDocument();

      // Send a message to the model
      const messageInput = screen.getByRole('textbox', { name: 'Task prompt' });
      await user.type(messageInput, 'What is the current date?');
      const submitButton = screen.getByRole('button', { name: 'Submit' });
      await user.click(submitButton);

      // Wait for the mutation to be called and verify the request parameters
      // With workspace "test", dropdown shows group "test" first (prompt-tuned/customized), then "default" (base).
      // First option is first in test group by name: entityStoreCustomizedModel1.
      await waitFor(() => {
        expect(mockMutateAsync).toHaveBeenCalledWith(
          expect.objectContaining({
            model: entityStoreCustomizedModel1.name,
            workspace: testWorkspace,
            messages: [{ role: 'user', content: 'What is the current date?' }],
            stream: true,
            tools: [JSON.parse(TOOL_JSON_EXAMPLE)],
          })
        );
      });
    });
  });
});
describe('Chat Disabled When Deployment Unavailable', () => {
  beforeEach(() => {
    mockMutateAsync.mockImplementation(() => Promise.resolve(createMockStream()));
    mockUseParams({
      [ROUTE_PARAMS.workspace]: testWorkspace,
    });
    mockUseModelChatAvailability({
      modelChatStatus: 'disabled',
      isChatAvailable: false,
    });
  });

  it('disables chat input and submit when model deployment is unavailable', async () => {
    const user = userEvent.setup();
    renderRoute();

    await waitFor(() => expect(screen.queryByTestId('spinner')).not.toBeInTheDocument(), {
      timeout: LG_SELECTOR_TIMEOUT,
    });

    // Select a model first
    const modelSelect = screen.getByTestId('model-select-v2-trigger');
    await waitFor(() => expect(modelSelect).toBeEnabled());
    await user.click(modelSelect);
    const options = await screen.findAllByTestId('model-dropdown-item');
    await user.click(options[0]);

    // Chat input and submit should be disabled
    const taskPromptInput = screen.getByRole('textbox', { name: 'Task prompt' });
    expect(taskPromptInput).toBeDisabled();
    const submitButton = screen.getByRole('button', { name: 'Submit' });
    expect(submitButton).toBeDisabled();
  });
});

describe('System Prompt Size Validation', () => {
  beforeEach(() => {
    mockUseParams({
      [ROUTE_PARAMS.workspace]: testWorkspace,
    });
  });

  // Helper function to set up playground with a model selected
  const setupPlaygroundWithModel = async () => {
    const user = userEvent.setup();
    renderRoute();

    await screen.findByText(`Model Parameters`);

    // Select model and wait for loading to complete first
    const modelSelect = screen.getByTestId('model-select-v2-trigger');
    await waitFor(() => expect(modelSelect).toBeEnabled());
    await user.click(modelSelect);
    const options = await screen.findAllByTestId('model-dropdown-item');
    await user.click(options[0]);
  };

  it('should disable chat when system prompt is too large', async () => {
    await setupPlaygroundWithModel();

    // Initially chat should be enabled
    const taskPromptInput = screen.getByRole('textbox', { name: 'Task prompt' });
    expect(taskPromptInput).toBeEnabled();

    // Enter large system prompt
    const systemInstructionsTextarea = screen.getByRole('textbox', { name: 'System Instructions' });
    fireEvent.change(systemInstructionsTextarea, { target: { value: LARGE_SYSTEM_PROMPT } });

    // Wait for validation to complete and chat to be disabled
    await waitFor(() => {
      expect(taskPromptInput).toBeDisabled();
    });
    const submitButton = screen.getByRole('button', { name: 'Submit' });
    expect(submitButton).toBeDisabled();
  });
});
describe('Model Creation Error Handling', () => {
  beforeEach(() => {
    mockUseParams({
      [ROUTE_PARAMS.workspace]: testWorkspace,
    });
  });

  // Helper to setup and attempt to save a model
  const attemptModelSave = async (modelName: string) => {
    const user = userEvent.setup();
    renderRoute();

    await screen.findByText('Prompt Tune a Model', undefined, { timeout: LG_SELECTOR_TIMEOUT });

    // Select model
    const modelSelect = screen.getByTestId('model-select-v2-trigger');
    await waitFor(() => expect(modelSelect).toBeEnabled());
    await user.click(modelSelect);
    const options = await screen.findAllByTestId('model-dropdown-item');
    await user.click(options[0]);

    // Click Save Model button
    const saveModelButton = screen.getByRole('button', { name: 'Save Model' });
    await user.click(saveModelButton);

    // Enter model name
    const modelNameInput = screen.getByRole('textbox', { name: 'Model Name' });
    await user.type(modelNameInput, modelName);

    // Click Save in modal
    const saveButton = screen.getByRole('button', { name: 'Save' });
    await user.click(saveButton);
  };

  it('should display error message for validation array errors', async () => {
    // Mock API to return validation error (422 with array of ValidationErrors)
    server.use(
      http.post(`${PLATFORM_BASE_URL}/apis/models/v2/workspaces/:workspace/models`, async () => {
        return HttpResponse.json(
          {
            detail: [
              {
                type: 'string_too_long',
                loc: ['body', 'name'],
                msg: 'String should have at most 255 characters',
              },
              {
                type: 'string_pattern_mismatch',
                loc: ['body', 'name'],
                msg: 'String should match pattern ^[a-z0-9-]+$',
              },
            ],
          },
          { status: 422 }
        );
      })
    );

    await attemptModelSave('test-model-with-validation-errors');

    // Wait for error toast to appear in the DOM
    await screen.findByText(
      'name: String should have at most 255 characters; name: String should match pattern ^[a-z0-9-]+$'
    );

    // Modal should still be open (not navigated away)
    expect(screen.getByRole('dialog', { name: 'Save Model' })).toBeInTheDocument();
  });

  // TODO: Unskip when test is no longer flaky
  it.skip('should display error message for string errors', async () => {
    suppressConsoleError('A model with this name already exists');

    // Mock API to return 409 conflict with simple string detail
    server.use(
      http.post(`${PLATFORM_BASE_URL}/apis/models/v2/workspaces/:workspace/models`, async () => {
        return HttpResponse.json(
          {
            detail: 'A model with this name already exists',
          },
          { status: 409 }
        );
      })
    );

    await attemptModelSave('duplicate-model');

    // Wait for error toast to appear in the DOM
    await screen.findByText('A model with this name already exists');

    // Modal should still be open
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  // TODO: Unskip when test is no longer flaky
  it.skip('should fall back to generic error message for unknown error formats', async () => {
    // 500 with no `detail`: getErrorMessage uses status + statusText (see api/common/utils).
    server.use(
      http.post(`${PLATFORM_BASE_URL}/apis/models/v2/workspaces/:workspace/models`, async () => {
        return HttpResponse.json(
          { message: 'Internal server error' },
          { status: 500, statusText: 'Internal Server Error' }
        );
      })
    );

    await attemptModelSave('err');

    // Assert on MockToastProvider output (data-testid) instead of document-wide findByText
    // so we are not racing ambiguous copy or toast animation timing.
    await waitFor(
      () => {
        expect(screen.getByTestId('mock-toast-error')).toHaveTextContent(/Internal Server Error/i);
      },
      { timeout: XL_SELECTOR_TIMEOUT }
    );

    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});
