// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FilesetPurpose, type FilesetOutput } from '@nemo/sdk/generated/platform/schema';
import { DatasetFileManagementSidePanel } from '@studio/components/DatasetFileManagementSidePanel';
import { GITKEEP_FILENAME } from '@studio/components/FilesTable/utils';
import { render } from '@studio/tests/util/render';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const { mockUseDatasetFileContent } = vi.hoisted(() => ({
  mockUseDatasetFileContent: vi.fn(() => ({
    data: undefined,
    isLoading: false,
    isError: false,
  })),
}));

const localFileset: FilesetOutput = {
  id: 'default/test-dataset',
  name: 'test-dataset',
  workspace: 'default',
  description: '',
  purpose: FilesetPurpose.dataset,
  storage: { type: 'local', path: '/tmp/test-dataset' } as FilesetOutput['storage'],
  metadata: {},
  custom_fields: {},
  project: '',
  created_at: '',
  updated_at: '',
};

const externalFileset: FilesetOutput = {
  ...localFileset,
  storage: {
    type: 'huggingface',
    repo_id: 'nvidia/test-dataset',
  } as FilesetOutput['storage'],
};

vi.mock('@studio/api/datasets/useDatasetFileContent', () => ({
  useDatasetFileContent: mockUseDatasetFileContent,
}));

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
    fileset: localFileset,
    onFolderChange: vi.fn(),
    onFileSelect: vi.fn(),
    onClose: vi.fn(),
  };

  const renderComponent = (props = {}) => {
    return render(<DatasetFileManagementSidePanel {...defaultProps} {...props} />);
  };

  beforeEach(() => {
    mockUseDatasetFileContent.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    });
  });

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

  it('renders the explorer directly when fileset metadata is unavailable', () => {
    renderComponent({ fileset: undefined });
    expect(screen.queryByRole('radio', { name: 'Dataset Card' })).not.toBeInTheDocument();
    expect(screen.getByTestId('dataset-details-search-input')).toBeInTheDocument();
  });

  it('waits for the file list before showing the external README empty state', () => {
    renderComponent({
      fileset: externalFileset,
      filesList: undefined,
      isLoading: true,
    });

    expect(screen.getByRole('radio', { name: 'Dataset Card' })).toBeInTheDocument();
    expect(screen.getByText('Loading README...')).toBeInTheDocument();
    expect(
      screen.queryByText('No README.md found at the root of this fileset.')
    ).not.toBeInTheDocument();
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
});
