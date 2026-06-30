// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FilesetOutput } from '@nemo/sdk/generated/platform/schema';
import { FilesetFileExplorer } from '@studio/components/filesets/FilesetFileExplorer';
import { GITKEEP_FILENAME } from '@studio/components/FilesTable/utils';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { server } from '@studio/mocks/node';
import { render } from '@studio/tests/util/render';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

vi.mock('@studio/providers/workers/useWorkers', () => ({
  useWorkers: () => ({
    createWorker: vi.fn(),
  }),
}));

vi.mock('@studio/hooks/useWorkspaceFromPath', () => ({
  useWorkspaceFromPath: () => 'default',
}));

describe('FilesetFileExplorer', () => {
  const defaultProps = {
    workspace: 'default',
    datasetName: 'test-dataset',
    datasetId: 'default/test-dataset',
    filesList: [],
    isLoading: false,
    isFilesFetching: false,
    onFileSelect: vi.fn(),
  };

  const renderComponent = (props = {}) => {
    return render(<FilesetFileExplorer {...defaultProps} {...props} />);
  };

  it('renders the file explorer toolbar', () => {
    renderComponent();
    expect(screen.getByTestId('dataset-details-search-input')).toBeInTheDocument();
  });

  it('displays loading state', () => {
    renderComponent({ isLoading: true });
    expect(screen.getByText('Loading files...')).toBeInTheDocument();
  });

  it('shows clear filters bar when search is active and clears on click', async () => {
    const user = userEvent.setup();
    renderComponent({
      filesList: [
        { path: 'file1.txt', size: 100, file_ref: 'oid1' },
        { path: 'file2.txt', size: 200, file_ref: 'oid2' },
      ],
    });

    const searchInput = screen.getByTestId('dataset-details-search-input');
    await user.type(searchInput, 'file1');

    expect(screen.getByText('1 Result')).toBeInTheDocument();
    const clearButton = screen.getByTestId('dataset-details-clear-filters');
    expect(clearButton).toBeInTheDocument();

    await user.click(clearButton);

    expect(screen.queryByTestId('dataset-details-clear-filters')).not.toBeInTheDocument();
    expect(screen.queryByText('1 Result')).not.toBeInTheDocument();
  });

  const filesetUrl = (path: string) =>
    `/apis/files/v2/workspaces/default/filesets/test-dataset/-/${path}`;

  it('hides .gitkeep placeholder files from the rendered list', async () => {
    renderComponent({
      filesList: [
        { path: 'file1.txt', size: 100, file_ref: 'oid1', file_url: filesetUrl('file1.txt') },
        {
          path: GITKEEP_FILENAME,
          size: 0,
          file_ref: 'gk-root',
          file_url: filesetUrl(GITKEEP_FILENAME),
        },
        {
          path: `empty-folder/${GITKEEP_FILENAME}`,
          size: 0,
          file_ref: 'gk-empty',
          file_url: filesetUrl(`empty-folder/${GITKEEP_FILENAME}`),
        },
      ],
    });

    await waitFor(() => {
      expect(screen.getByText('file1.txt')).toBeInTheDocument();
      expect(screen.getByText('empty-folder')).toBeInTheDocument();
    });

    expect(screen.queryByText(GITKEEP_FILENAME)).not.toBeInTheDocument();
  });

  it('falls back to the empty state when the dataset contains only .gitkeep files', async () => {
    renderComponent({
      filesList: [
        {
          path: GITKEEP_FILENAME,
          size: 0,
          file_ref: 'gk-root',
          file_url: filesetUrl(GITKEEP_FILENAME),
        },
      ],
    });

    expect(await screen.findByText('No Files')).toBeInTheDocument();
  });

  describe('read-only gating by storage.type', () => {
    const stubFileset = (storageType: FilesetOutput['storage']['type']): FilesetOutput =>
      ({
        id: 'default/test-dataset',
        name: 'test-dataset',
        workspace: 'default',
        description: '',
        purpose: 'dataset',
        storage: { type: storageType } as FilesetOutput['storage'],
        metadata: {},
        custom_fields: {},
        project: 'default',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      }) as FilesetOutput;

    const stubRetrieve = (storageType: FilesetOutput['storage']['type']) => {
      server.use(
        http.get(`${PLATFORM_BASE_URL}/apis/files/v2/workspaces/:workspace/filesets/:name`, () =>
          HttpResponse.json(stubFileset(storageType))
        )
      );
    };

    it('shows New Directory + Upload File toolbar buttons for local fileset', async () => {
      stubRetrieve('local');
      renderComponent({
        filesList: [
          { path: 'file1.txt', size: 100, file_ref: 'oid1', file_url: filesetUrl('file1.txt') },
        ],
      });
      expect(await screen.findByTestId('dataset-details-new-directory-button')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Upload File' })).toBeInTheDocument();
    });

    it.each<FilesetOutput['storage']['type']>(['huggingface', 'ngc', 's3'])(
      'hides New Directory + Upload File toolbar buttons for %s fileset',
      async (storageType) => {
        stubRetrieve(storageType);
        renderComponent({
          filesList: [
            { path: 'file1.txt', size: 100, file_ref: 'oid1', file_url: filesetUrl('file1.txt') },
          ],
        });
        // Wait for the fileset query to resolve; assert via a stable surface
        // (search input is always present) before checking absence.
        await screen.findByTestId('dataset-details-search-input');
        await waitFor(() => {
          expect(
            screen.queryByTestId('dataset-details-new-directory-button')
          ).not.toBeInTheDocument();
        });
        expect(screen.queryByRole('button', { name: 'Upload File' })).not.toBeInTheDocument();
      }
    );

    it('shows empty-state action buttons for local fileset', async () => {
      stubRetrieve('local');
      renderComponent({ filesList: [] });
      await screen.findByText('No Files');
      // Toolbar + empty-state both expose these buttons; wait for at least
      // one of each since they only mount after the fileset query resolves.
      expect(
        (await screen.findAllByRole('button', { name: 'New Directory' })).length
      ).toBeGreaterThan(0);
      expect(
        (await screen.findAllByRole('button', { name: 'Upload File' })).length
      ).toBeGreaterThan(0);
    });

    it('hides empty-state action buttons and shows read-only copy for external fileset', async () => {
      stubRetrieve('huggingface');
      renderComponent({ filesList: [] });
      await screen.findByText('No Files');
      await waitFor(() => {
        expect(screen.getByText('This fileset is read-only.')).toBeInTheDocument();
      });
      expect(screen.queryByRole('button', { name: 'New Directory' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Upload File' })).not.toBeInTheDocument();
    });
  });

  it('renders extraColumns: header in the table head + cell-per-file in rows', async () => {
    renderComponent({
      filesList: [
        { path: 'a.jsonl', size: 100, file_ref: 'oid-a', file_url: filesetUrl('a.jsonl') },
        { path: 'b.jsonl', size: 200, file_ref: 'oid-b', file_url: filesetUrl('b.jsonl') },
      ],
      extraColumns: [
        {
          header: 'Schema',
          cell: (node: { type: string; path: string }) =>
            node.type === 'file' ? `schema-for-${node.path}` : null,
        },
      ],
    });

    // Header rendered.
    expect(await screen.findByText('Schema')).toBeInTheDocument();
    // Cell rendered for each file row.
    expect(screen.getByText('schema-for-a.jsonl')).toBeInTheDocument();
    expect(screen.getByText('schema-for-b.jsonl')).toBeInTheDocument();
  });
});
