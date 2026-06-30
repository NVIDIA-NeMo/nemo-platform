// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ModelEntitysPage } from '@nemo/sdk/generated/platform/schema';
import { CustomModelsDataView } from '@studio/components/dataViews/CustomModelsDataView';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import {
  entityStoreBaseModel1,
  entityStoreCustomizedModel1,
  entityStorePromptTunedModel1,
} from '@studio/mocks/entity-store/models';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { server } from '@studio/mocks/node';
import { getCustomizationJobListRoute } from '@studio/routes/utils';
import { renderRoute } from '@studio/tests/util/render';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

const MODELS_URL = `${PLATFORM_BASE_URL}/apis/models/v2/workspaces/:workspace/models`;
const ADAPTER_DELETE_URL = `${PLATFORM_BASE_URL}/apis/models/v2/workspaces/:workspace/models/:modelName/adapters/:adapter`;

const modelsPage: ModelEntitysPage = {
  data: [entityStoreBaseModel1, entityStorePromptTunedModel1, entityStoreCustomizedModel1],
  pagination: {
    page: 1,
    page_size: 30,
    current_page_size: 30,
    total_pages: 1,
    total_results: 3,
  },
};

const emptyModelsPage: ModelEntitysPage = {
  data: [],
  pagination: {
    page: 1,
    page_size: 30,
    current_page_size: 30,
    total_pages: 0,
    total_results: 0,
  },
};

const renderComponent = () =>
  renderRoute(<CustomModelsDataView workspace={workspace1.workspace} />, {
    history: getCustomizationJobListRoute(workspace1.workspace),
    routes: [
      {
        path: ROUTES.workspace.customizationJobList,
        element: <CustomModelsDataView workspace={workspace1.workspace} />,
      },
    ],
  });

vi.mock('@nemo/common/src/components/DataView/StudioDataView', async () => {
  const { studioDataViewMock } = await import('@studio/tests/util');
  return studioDataViewMock();
});

describe('CustomModelsDataView', () => {
  it('renders the empty state when no models are available', async () => {
    server.use(http.get(MODELS_URL, () => HttpResponse.json(emptyModelsPage)));

    renderComponent();

    expect(await screen.findByText('Manage Custom Models')).toBeInTheDocument();
  });

  it('renders the error state when there is an error fetching models', async () => {
    server.use(http.get(MODELS_URL, () => HttpResponse.error()));

    renderComponent();

    expect(await screen.findByText('Loading Error')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('renders the expected columns and model data', async () => {
    server.use(http.get(MODELS_URL, () => HttpResponse.json(modelsPage)));

    renderComponent();

    await waitFor(() => expect(screen.queryByTestId('spinner')).not.toBeInTheDocument());

    const columns = ['Name', 'Base Model', 'Created'];
    for (const columnHeader of columns) {
      expect(await screen.findByRole('columnheader', { name: columnHeader })).toBeInTheDocument();
    }

    expect(screen.getAllByText(entityStoreBaseModel1.name).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('row').length).toBeGreaterThan(0);
  });

  it('deletes an adapter via the correct API endpoint', async () => {
    const user = userEvent.setup();
    const adapterDeleteHandler = vi.fn();
    const adapterName = entityStoreCustomizedModel1.adapters![0].name;

    server.use(
      http.get(MODELS_URL, () => HttpResponse.json(modelsPage)),
      http.delete(ADAPTER_DELETE_URL, ({ params }) => {
        adapterDeleteHandler(params);
        return new HttpResponse(null, { status: 204 });
      })
    );

    renderComponent();

    await waitFor(() => expect(screen.queryByTestId('spinner')).not.toBeInTheDocument());

    // Sub-rows are expanded by default — find the adapter and open its actions menu
    await screen.findByText(adapterName);
    const actionButtons = screen.getAllByRole('button', { name: /actions/i });
    const adapterActionButton = actionButtons[actionButtons.length - 1];
    await user.click(adapterActionButton);

    // Click "Delete Adapter" in the menu
    await user.click(await screen.findByRole('menuitem', { name: 'Delete Adapter' }));

    // Confirm deletion in the modal
    expect(await screen.findByText('Delete Adapter')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => {
      expect(adapterDeleteHandler).toHaveBeenCalledWith(
        expect.objectContaining({
          modelName: entityStoreCustomizedModel1.name,
          adapter: adapterName,
        })
      );
    });
  });
});
