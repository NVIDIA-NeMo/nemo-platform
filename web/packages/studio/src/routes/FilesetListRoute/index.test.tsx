// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FilesetOutput } from '@nemo/sdk/generated/platform/schema';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { server } from '@studio/mocks/node';
import { FilesetListRoute } from '@studio/routes/FilesetListRoute';
import { LG_SELECTOR_TIMEOUT } from '@studio/tests/util/constants';
import { mockUseParams } from '@studio/tests/util/mockUseParams';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

// Mock child components to isolate testing
vi.mock('@studio/routes/FilesetListRoute/ActionMenu', () => ({
  ActionMenu: vi.fn(({ dataset, onNavigateToDetails, onDatasetUpdated, onDatasetDeleted }) => (
    <div data-testid={`action-menu-${dataset.name}`}>
      <button
        onClick={() => onNavigateToDetails?.(dataset)}
        data-testid={`navigate-to-details-${dataset.name}`}
      >
        View Details
      </button>
      <button
        onClick={() => onDatasetUpdated?.({ ...dataset, description: 'Updated description' })}
        data-testid={`update-dataset-${dataset.name}`}
      >
        Update
      </button>
      <button
        onClick={() => onDatasetDeleted?.(dataset)}
        data-testid={`delete-dataset-${dataset.name}`}
      >
        Delete
      </button>
    </div>
  )),
}));

vi.mock('@studio/routes/FilesetListRoute/DatasetBulkDeleteModal', () => ({
  DatasetBulkDeleteModal: vi.fn(({ selectedDatasets, onConfirmSuccess }) => (
    <div data-testid="bulk-delete-modal">
      <span>Bulk Delete Modal</span>
      <span data-testid="selected-datasets-count">{selectedDatasets.length}</span>
      <button onClick={() => onConfirmSuccess?.()} data-testid="confirm-bulk-delete">
        Confirm Delete
      </button>
    </div>
  )),
}));

// Mock the route utils
vi.mock('@studio/routes/utils', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@studio/routes/utils')>();
  return {
    ...actual,
    getFilesetDetailsRoute: (project: string, datasetName: string) =>
      `/projects/${project}/filesets/${datasetName}`,
    getNewFilesetRoute: (project: string) => `/projects/${project}/filesets/new`,
  };
});

vi.mock('@studio/routes/FilesetListRoute/PanelManagement', () => ({
  PanelManagement: vi.fn(({ workspace }) => <div data-testid="panel-management">{workspace}</div>),
}));

const renderRoute = () => {
  return render(
    <TestProviders>
      <MemoryRouter>
        <FilesetListRoute />
      </MemoryRouter>
    </TestProviders>
  );
};

vi.mock('use-debounce', () => ({
  useDebounce: (value: unknown) => [value, () => {}],
}));

describe('FilesetListRoute', () => {
  let user: ReturnType<typeof userEvent.setup>;

  // Mock datasets for testing (using FilesetOutput structure for V2 API)
  const mockDatasets: FilesetOutput[] = [
    {
      id: 'dataset-1-id',
      name: 'dataset-1',
      workspace: 'default',
      description: 'First test dataset',
      purpose: 'dataset',
      storage: { type: 'local', path: '/data/dataset-1' },
      metadata: {},
      custom_fields: {},
      project: 'default',
      created_at: '2024-12-17T16:08:56.880768',
      updated_at: '2024-12-17T16:08:56.880771',
    },
    {
      id: 'dataset-2-id',
      name: 'dataset-2',
      workspace: 'default',
      description: 'Second test dataset',
      purpose: 'dataset',
      storage: { type: 'local', path: '/data/dataset-2' },
      metadata: {},
      custom_fields: {},
      project: 'default',
      created_at: '2024-12-17T15:08:56.880768',
      updated_at: '2024-12-17T15:08:56.880771',
    },
    {
      id: 'dataset-3-id',
      name: 'searchable-dataset',
      workspace: 'default',
      description: 'Dataset for search testing',
      purpose: 'dataset',
      storage: { type: 'local', path: '/data/searchable-dataset' },
      metadata: {},
      custom_fields: {},
      project: 'default',
      created_at: '2024-12-17T14:08:56.880768',
      updated_at: '2024-12-17T14:08:56.880771',
    },
  ];

  const mockDatasetsResponse = {
    object: 'list',
    data: mockDatasets,
    pagination: {
      page: 1,
      page_size: 50,
      current_page_size: 3,
      total_pages: 1,
      total_results: 3,
    },
    sort: '-created_at',
  };

  beforeEach(() => {
    user = userEvent.setup();
    mockUseParams({
      [ROUTE_PARAMS.workspace]: workspace1.workspace,
    });
    server.use(
      http.get(`${PLATFORM_BASE_URL}/apis/files/v2/workspaces/:workspace/filesets`, () =>
        HttpResponse.json(mockDatasetsResponse)
      )
    );
  });

  describe('Basic Rendering', () => {
    it('renders the filesets list page with header and create button', async () => {
      renderRoute();

      // Target the specific page header element rather than any "Filesets" text
      expect(
        await screen.findByTestId('nv-page-header-heading', undefined, {
          timeout: LG_SELECTOR_TIMEOUT,
        })
      ).toHaveTextContent('Filesets');
      expect(screen.getByRole('link', { name: 'Create Fileset' })).toBeInTheDocument();
    });
  });

  describe('Search Functionality', () => {
    // Note: The V2 fileset API (FilesetFilter) does not support name-based filtering.
    // Only purpose, storage_type, and created_at filters are available.
    // These tests are skipped until server-side name search is implemented.
    it.skip('filters datasets when search query is entered', async () => {
      renderRoute();

      const searchInput = await screen.findByPlaceholderText('Search datasets by name');

      await user.click(searchInput);
      await user.paste('searchable');

      // With mocked debounce, results appear immediately
      expect(await screen.findByText('searchable-dataset')).toBeInTheDocument();
      expect(screen.queryByText('dataset-1')).not.toBeInTheDocument();
      expect(screen.queryByText('dataset-2')).not.toBeInTheDocument();
    });

    it.skip('clears selected datasets when search query changes', async () => {
      renderRoute();

      // First select a dataset
      const checkbox = await screen.findByLabelText('Select dataset dataset-1');
      await user.click(checkbox);

      // Verify selection worked
      expect(await screen.findByText('1 row selected')).toBeInTheDocument();

      // Now search, which should clear selection
      const searchInput = screen.getByPlaceholderText('Search datasets by name');
      await user.click(searchInput);
      await user.paste('searchable');

      await waitFor(() => expect(screen.queryByText('1 row selected')).not.toBeInTheDocument());
    });
  });

  // Dataset selection checkbox behavior (select, deselect, select-all, indeterminate)
  // is provided by KUI DataView's built-in rowSelectionColumn and tested upstream.

  describe('Navigation', () => {
    it('navigates to dataset details when a dataset row is clicked', async () => {
      const listPath = `/projects/${workspace1.workspace}/filesets`;

      const router = createMemoryRouter(
        [
          {
            path: '/projects/:workspace/filesets',
            element: (
              <TestProviders>
                <FilesetListRoute />
              </TestProviders>
            ),
          },
          {
            path: '/projects/:workspace/filesets/:filesetId',
            element: <div data-testid="dataset-details-route" />,
          },
        ],
        { initialEntries: [listPath] }
      );

      render(<RouterProvider router={router} />);

      // 1. Wait for data to load and the row click handler to be wired up.
      //    The "Open row" button is injected by useRowClick into every row once
      //    the click handler is active — its presence signals the table is ready.
      await waitFor(
        () => {
          screen.getByText('dataset-1');
          expect(screen.getAllByRole('button', { name: 'Open row' }).length).toBeGreaterThan(0);
        },
        { timeout: LG_SELECTOR_TIMEOUT }
      );
      // 2. Activate the first row via keyboard on the "Open row" button.
      //    Keyboard activation calls onActivate() directly, bypassing click-delegation
      //    which is unreliable in happy-dom + user-event 14.6.x (pointer coords change).
      const openRowButton = screen.getAllByRole('button', { name: 'Open row' })[0];
      openRowButton.focus();
      await user.keyboard('{Enter}');

      // 3. Wait for navigation to complete
      await waitFor(
        () => {
          expect(screen.getByTestId('dataset-details-route')).toBeInTheDocument();
        },
        { timeout: LG_SELECTOR_TIMEOUT }
      );
    });

    it('renders action menu with navigation button', async () => {
      renderRoute();

      await screen.findByTestId('navigate-to-details-dataset-1', undefined, {
        timeout: LG_SELECTOR_TIMEOUT,
      });
    });
  });
});
