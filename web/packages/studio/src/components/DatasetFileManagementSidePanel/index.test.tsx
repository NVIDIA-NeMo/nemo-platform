// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DatasetFileManagementSidePanel } from '@studio/components/DatasetFileManagementSidePanel';
import { GITKEEP_FILENAME } from '@studio/components/FilesTable/utils';
import { render } from '@studio/tests/util/render';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@studio/providers/workers/useWorkers', () => ({
  useWorkers: () => ({
    createWorker: vi.fn(),
  }),
}));

vi.mock('@studio/hooks/useWorkspaceFromPath', () => ({
  useWorkspaceFromPath: () => 'default',
}));

describe('DatasetFileManagementSidePanel', () => {
  const defaultProps = {
    open: true,
    workspace: 'default',
    datasetName: 'test-dataset',
    datasetId: 'default/test-dataset',
    filesList: [],
    isLoading: false,
    isFilesFetching: false,
    onFolderChange: vi.fn(),
    onFileSelect: vi.fn(),
    onClose: vi.fn(),
  };

  const renderComponent = (props = {}) => {
    return render(<DatasetFileManagementSidePanel {...defaultProps} {...props} />);
  };

  it('renders the side panel', () => {
    renderComponent();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('displays loading state', () => {
    renderComponent({
      isLoading: true,
    });
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

  it('renders the inline file preview instead of the explorer when a file is selected', async () => {
    renderComponent({
      filesList: [
        { path: 'folder1/file.txt', size: 100, file_ref: 'oid1', file_url: filesetUrl('file.txt') },
      ],
      selectedFilePath: 'folder1/file.txt',
    });

    // File breadcrumb segments are shown in the heading...
    await waitFor(() => {
      expect(screen.getByText('folder1')).toBeInTheDocument();
      expect(screen.getByText('file.txt')).toBeInTheDocument();
    });

    // ...and the explorer (search/toolbar) is not rendered.
    expect(screen.queryByTestId('dataset-details-search-input')).not.toBeInTheDocument();
  });

  it('navigates to the fileset root when the fileset breadcrumb is clicked in preview', async () => {
    const user = userEvent.setup();
    const onFolderChange = vi.fn();
    renderComponent({
      filesList: [
        { path: 'file.txt', size: 100, file_ref: 'oid1', file_url: filesetUrl('file.txt') },
      ],
      selectedFilePath: 'file.txt',
      onFolderChange,
    });

    await user.click(await screen.findByRole('button', { name: 'test-dataset' }));

    expect(onFolderChange).toHaveBeenCalledWith();
  });
});
