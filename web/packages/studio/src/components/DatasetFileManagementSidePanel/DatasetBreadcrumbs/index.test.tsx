// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DatasetBreadcrumbs } from '@studio/components/DatasetFileManagementSidePanel/DatasetBreadcrumbs';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

interface RenderOptions {
  datasetName: string;
  currentFolder?: string;
  onFolderChange?: (folderPath?: string) => void;
}

const renderComponent = ({
  datasetName,
  currentFolder,
  onFolderChange = vi.fn(),
}: RenderOptions) => {
  return {
    ...render(
      <DatasetBreadcrumbs
        datasetName={datasetName}
        currentFolder={currentFolder}
        onFolderChange={onFolderChange}
      />
    ),
    onFolderChange,
  };
};

describe('DatasetBreadcrumbs', () => {
  describe('when no currentFolder is provided', () => {
    it('renders only the root breadcrumb with dataset name', () => {
      const datasetName = 'my-test-dataset';
      renderComponent({ datasetName });

      // Should render the breadcrumbs container
      expect(screen.getByTestId('dataset-breadcrumbs')).toBeInTheDocument();

      // Should render the dataset name as a button
      const datasetButton = screen.getByRole('button', { name: datasetName });
      expect(datasetButton).toBeInTheDocument();
    });

    it('calls onFolderChange with undefined when root breadcrumb is clicked', async () => {
      const user = userEvent.setup();
      const datasetName = 'my-test-dataset';
      const { onFolderChange } = renderComponent({ datasetName });

      const datasetButton = screen.getByRole('button', { name: datasetName });
      await user.click(datasetButton);

      expect(onFolderChange).toHaveBeenCalledWith();
      expect(onFolderChange).toHaveBeenCalledTimes(1);
    });
  });

  describe('when currentFolder has a single folder', () => {
    it('renders root and folder breadcrumbs', () => {
      const datasetName = 'my-dataset';
      renderComponent({ datasetName, currentFolder: 'documents' });

      // Should render both the dataset root and the folder
      expect(screen.getByRole('button', { name: datasetName })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'documents' })).toBeInTheDocument();
    });

    it('calls onFolderChange with correct path when folder breadcrumb is clicked', async () => {
      const user = userEvent.setup();
      const datasetName = 'my-dataset';
      const { onFolderChange } = renderComponent({ datasetName, currentFolder: 'documents' });

      const folderButton = screen.getByRole('button', { name: 'documents' });
      await user.click(folderButton);

      expect(onFolderChange).toHaveBeenCalledWith('documents');
      expect(onFolderChange).toHaveBeenCalledTimes(1);
    });

    it('calls onFolderChange with undefined when root breadcrumb is clicked', async () => {
      const user = userEvent.setup();
      const datasetName = 'my-dataset';
      const { onFolderChange } = renderComponent({ datasetName, currentFolder: 'documents' });

      const rootButton = screen.getByRole('button', { name: datasetName });
      await user.click(rootButton);

      expect(onFolderChange).toHaveBeenCalledWith();
      expect(onFolderChange).toHaveBeenCalledTimes(1);
    });
  });

  describe('when currentFolder has nested folders', () => {
    it('renders all folder levels in breadcrumbs', () => {
      const datasetName = 'my-dataset';
      renderComponent({ datasetName, currentFolder: 'documents/pdfs/reports' });

      // Should render the dataset root and all folder levels
      expect(screen.getByRole('button', { name: datasetName })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'documents' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'pdfs' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'reports' })).toBeInTheDocument();
    });

    it('calls onFolderChange with correct path for each breadcrumb level', async () => {
      const user = userEvent.setup();
      const datasetName = 'my-dataset';
      const { onFolderChange } = renderComponent({
        datasetName,
        currentFolder: 'documents/pdfs/reports',
      });

      // Click root breadcrumb
      const rootButton = screen.getByRole('button', { name: datasetName });
      await user.click(rootButton);
      expect(onFolderChange).toHaveBeenCalledWith();

      // Click documents breadcrumb
      const documentsButton = screen.getByRole('button', { name: 'documents' });
      await user.click(documentsButton);
      expect(onFolderChange).toHaveBeenCalledWith('documents');

      // Click pdfs breadcrumb
      const pdfsButton = screen.getByRole('button', { name: 'pdfs' });
      await user.click(pdfsButton);
      expect(onFolderChange).toHaveBeenCalledWith('documents/pdfs');

      // Click reports breadcrumb
      const reportsButton = screen.getByRole('button', { name: 'reports' });
      await user.click(reportsButton);
      expect(onFolderChange).toHaveBeenCalledWith('documents/pdfs/reports');
    });
  });

  describe('when currentFolder is an empty string', () => {
    it('renders only the root breadcrumb', () => {
      const datasetName = 'empty-folder-dataset';
      renderComponent({ datasetName, currentFolder: '' });

      // Should only render the dataset name
      expect(screen.getByRole('button', { name: datasetName })).toBeInTheDocument();

      // Should not render any additional breadcrumbs
      const allButtons = screen.getAllByRole('button');
      expect(allButtons).toHaveLength(1);
    });
  });
});
