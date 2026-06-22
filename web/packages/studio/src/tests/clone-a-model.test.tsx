// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ModelEntity, ModelEntitysPage } from '@nemo/sdk/generated/platform/schema';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTES, ROUTE_PARAMS } from '@studio/constants/routes';
import {
  entityStoreBaseModel1,
  entityStorePromptTunedModel1,
} from '@studio/mocks/entity-store/models';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { server } from '@studio/mocks/node';
import { CustomizationJobListRoute } from '@studio/routes/CustomizationJobListRoute';
import { PromptTuningFormRoute } from '@studio/routes/PromptTuningFormRoute';
import { PROMPT_TUNING_HEADING_TEXT } from '@studio/routes/PromptTuningFormRoute/constants';
import { getWorkspaceCustomizationJobListRoute } from '@studio/routes/utils';
import { LG_SELECTOR_TIMEOUT, XL_SELECTOR_TIMEOUT } from '@studio/tests/util/constants';
import { mockUseParams } from '@studio/tests/util/mockUseParams';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

const baseModel = entityStoreBaseModel1;
const workspace = workspace1;

// Helper to render the route with proper router setup
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

/**
 * TODO: Unskip if/when we support cloning models.
 */
describe.skip('Clone a model', () => {
  beforeEach(() => {
    mockUseParams({
      [ROUTE_PARAMS.workspace]: workspace.workspace,
    });

    server.use(
      http.get<never, never, ModelEntity>(
        `${PLATFORM_BASE_URL}/apis/models/v2/workspaces/${baseModel.workspace}/models/${baseModel.name}`,
        async () => HttpResponse.json(baseModel)
      )
    );
  });
  it('A user can clone a model from the table view', async () => {
    server.use(
      http.get<never, never, ModelEntitysPage>(
        `${PLATFORM_BASE_URL}/apis/models/v2/workspaces/default/models`,
        async () =>
          HttpResponse.json({
            data: [entityStorePromptTunedModel1],
          })
      )
    );
    const user = userEvent.setup();
    renderRoute();

    // open trigger menu
    const triggerMenu = (
      await screen.findAllByTestId('quick-actions-menu-trigger', undefined, {
        timeout: LG_SELECTOR_TIMEOUT,
      })
    )[0];
    expect(triggerMenu).toBeInTheDocument();

    // click clone and edit
    await user.click(triggerMenu);
    fireEvent.click(screen.getByText('Clone and Edit'));

    // check that we're on the playground view
    await waitFor(() => expect(document.title).toBe(`${PROMPT_TUNING_HEADING_TEXT} - Studio`), {
      timeout: XL_SELECTOR_TIMEOUT,
    });
    const saveButton = screen.getByRole('button', { name: 'Save Model' });
    await waitFor(() => expect(saveButton).toBeInTheDocument());

    // check that the hyperparameters have populated
    const accordionTitle = screen.getByText('Hyperparameters');
    await user.click(accordionTitle);

    const temperatureInputNew = screen.getByLabelText('temperature-slider_text_input');
    await waitFor(() =>
      expect(temperatureInputNew).toHaveValue(
        (entityStorePromptTunedModel1.custom_fields?.inference_params as { temperature?: number })
          ?.temperature
      )
    );
    const maxTokenInputNew = screen.getByLabelText('max_tokens-slider_text_input');
    await waitFor(() =>
      expect(maxTokenInputNew).toHaveValue(
        (entityStorePromptTunedModel1.custom_fields?.inference_params as { max_tokens?: number })
          ?.max_tokens
      )
    );

    // check that the model name has populated
    await user.click(saveButton);
    const modelName = screen.getByRole('textbox', { name: 'Model Name' });
    await waitFor(() => expect(modelName).toHaveValue(`${entityStorePromptTunedModel1.name}_copy`));
  });
});
