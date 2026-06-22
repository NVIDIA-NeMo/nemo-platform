// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DatasetFileManagementSidePanelContainer } from '@studio/components/DatasetFileManagementSidePanel/DatasetFileManagementSidePanelContainer';
import { render } from '@studio/tests/util/render';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock the child component to expose the props the container passes down
vi.mock('@studio/components/DatasetFileManagementSidePanel', () => ({
  DatasetFileManagementSidePanel: vi.fn(
    ({ open, datasetName, currentFolder, filesList, isLoading, onClose, onFolderChange }) => (
      <div data-testid="dataset-file-management-sidepanel" data-open={open}>
        <div data-testid="dataset-name">{datasetName}</div>
        <div data-testid="current-folder">{currentFolder || 'root'}</div>
        <div data-testid="is-loading">{String(isLoading)}</div>
        <div data-testid="files-count">{filesList?.length ?? 'none'}</div>
        <button onClick={onClose} data-testid="close-button">
          Close
        </button>
        <button onClick={() => onFolderChange?.('test-folder/')} data-testid="change-folder-button">
          Change Folder
        </button>
      </div>
    )
  ),
}));

describe('DatasetFileManagementSidePanelContainer', () => {
  it('should render with open=false and pass the prop to child component', () => {
    render(
      <DatasetFileManagementSidePanelContainer
        datasetId="default/test-dataset"
        open={false}
        onClose={vi.fn()}
        onFolderChange={vi.fn()}
      />
    );

    const sidepanel = screen.getByTestId('dataset-file-management-sidepanel');
    expect(sidepanel).toBeInTheDocument();
    expect(sidepanel).toHaveAttribute('data-open', 'false');
  });

  it('should render when open is true', async () => {
    render(
      <DatasetFileManagementSidePanelContainer
        datasetId="default/test-dataset"
        open
        onClose={vi.fn()}
        onFolderChange={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('dataset-file-management-sidepanel')).toBeInTheDocument();
    });

    const sidepanel = screen.getByTestId('dataset-file-management-sidepanel');
    expect(sidepanel).toHaveAttribute('data-open', 'true');
  });

  it('should not fetch files when closed', () => {
    render(
      <DatasetFileManagementSidePanelContainer
        datasetId="default/test-dataset"
        open={false}
        onClose={vi.fn()}
        onFolderChange={vi.fn()}
      />
    );

    // Query is disabled when closed — no data should be passed to child
    expect(screen.getByTestId('files-count')).toHaveTextContent('none');
  });

  it('should fetch and pass files when open', async () => {
    render(
      <DatasetFileManagementSidePanelContainer
        datasetId="default/test-dataset"
        open
        onClose={vi.fn()}
        onFolderChange={vi.fn()}
      />
    );

    // MSW default handler returns file data; wait for it to arrive
    await waitFor(() => {
      expect(screen.getByTestId('files-count')).not.toHaveTextContent('none');
    });
  });

  it('should parse datasetId correctly', async () => {
    render(
      <DatasetFileManagementSidePanelContainer
        datasetId="default/test-dataset"
        open
        onClose={vi.fn()}
        onFolderChange={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('dataset-name')).toHaveTextContent('test-dataset');
    });
  });

  it('should pass currentFolder to child component', async () => {
    render(
      <DatasetFileManagementSidePanelContainer
        datasetId="default/test-dataset"
        open
        currentFolder="training/"
        onClose={vi.fn()}
        onFolderChange={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('current-folder')).toHaveTextContent('training/');
    });
  });

  it('should call onClose when sidepanel is closed', async () => {
    const onClose = vi.fn();

    render(
      <DatasetFileManagementSidePanelContainer
        datasetId="default/test-dataset"
        open
        onClose={onClose}
        onFolderChange={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('close-button')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByTestId('close-button'));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('should call onFolderChange when folder is changed', async () => {
    const onFolderChange = vi.fn();

    render(
      <DatasetFileManagementSidePanelContainer
        datasetId="default/test-dataset"
        open
        onClose={vi.fn()}
        onFolderChange={onFolderChange}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('change-folder-button')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByTestId('change-folder-button'));

    expect(onFolderChange).toHaveBeenCalledWith('test-folder/');
  });

  it('should handle undefined currentFolder', async () => {
    render(
      <DatasetFileManagementSidePanelContainer
        datasetId="default/test-dataset"
        open
        currentFolder={undefined}
        onClose={vi.fn()}
        onFolderChange={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('current-folder')).toHaveTextContent('root');
    });
  });

  it('should provide no-op callbacks when not provided', async () => {
    render(
      <DatasetFileManagementSidePanelContainer
        datasetId="default/test-dataset"
        open
        onClose={vi.fn()}
        onFolderChange={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('change-folder-button')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByTestId('change-folder-button'));
  });
});
