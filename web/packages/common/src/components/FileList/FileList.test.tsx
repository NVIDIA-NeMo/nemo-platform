// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  FileList,
  type FileListItem,
  type FileListError,
} from '@nemo/common/src/components/FileList/index';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('FileList', () => {
  const user = userEvent.setup();
  const mockOnDeleteFile = vi.fn();
  const mockOnPreviewFile = vi.fn();

  const mockFile: FileListItem = {
    dataset: {
      id: 'workspace/dataset',
      name: 'dataset',
      workspace: 'workspace',
      description: '',
      purpose: 'dataset',
      storage: { type: 'local', path: '/data' },
      metadata: {},
      custom_fields: {},
      project: 'default',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    },
    path: 'train.csv',
    url: 'fileset://workspace/dataset/train.csv',
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('rendering', () => {
    it('renders file list with single file', () => {
      render(<FileList files={[mockFile]} />);

      expect(screen.getByText('train.csv')).toBeInTheDocument();
    });

    it('renders label when provided', () => {
      render(<FileList files={[mockFile]} label="Data Source Target" />);

      expect(screen.getByText('Data Source Target')).toBeInTheDocument();
      expect(screen.getByText('train.csv')).toBeInTheDocument();
    });

    it('does not render label when not provided', () => {
      render(<FileList files={[mockFile]} />);

      expect(screen.queryByText('Data Source Target')).not.toBeInTheDocument();
    });

    it('renders dividers between file items', () => {
      const multipleFiles: FileListItem[] = [mockFile, { ...mockFile, path: 'test.csv' }];

      render(<FileList files={multipleFiles} />);

      const dividers = screen.getAllByRole('separator');
      // For 2 files: divider before first, divider before second, divider after last = 3 dividers
      expect(dividers.length).toBe(3);
    });
  });

  describe('error items', () => {
    it('renders error items with error styling', () => {
      const errorItem: FileListError = { error: 'No Training Data Found' };

      render(<FileList files={[errorItem]} />);

      expect(screen.getByText('No Training Data Found')).toBeInTheDocument();
    });

    it('renders mixed file and error items', () => {
      const mixedFiles: (FileListItem | FileListError)[] = [
        mockFile,
        { error: 'Validation file missing' },
      ];

      render(<FileList files={mixedFiles} />);

      expect(screen.getByText('train.csv')).toBeInTheDocument();
      expect(screen.getByText('Validation file missing')).toBeInTheDocument();
    });
  });

  describe('preview functionality', () => {
    it('renders preview button for each file by default', () => {
      render(<FileList files={[mockFile]} onPreviewFile={mockOnPreviewFile} />);

      expect(screen.getByLabelText('Preview file')).toBeInTheDocument();
    });

    it('calls onPreviewFile when preview button is clicked', async () => {
      render(<FileList files={[mockFile]} onPreviewFile={mockOnPreviewFile} />);

      const previewButton = screen.getByLabelText('Preview file');
      await user.click(previewButton);

      expect(mockOnPreviewFile).toHaveBeenCalledWith(mockFile);
    });

    it('hides preview button when allowPreview is false', () => {
      render(<FileList files={[mockFile]} allowPreview={false} />);

      expect(screen.queryByLabelText('Preview file')).not.toBeInTheDocument();
    });

    it('does not render preview button for error items', () => {
      const errorItem: FileListError = { error: 'Error message' };

      render(<FileList files={[errorItem]} onPreviewFile={mockOnPreviewFile} />);

      expect(screen.queryByLabelText('Preview file')).not.toBeInTheDocument();
    });
  });

  describe('delete functionality', () => {
    it('renders delete button for each file by default', () => {
      render(<FileList files={[mockFile]} onDeleteFile={mockOnDeleteFile} />);

      expect(screen.getByLabelText('Delete file')).toBeInTheDocument();
    });

    it('calls onDeleteFile with filepath when delete button is clicked', async () => {
      render(<FileList files={[mockFile]} onDeleteFile={mockOnDeleteFile} />);

      const deleteButton = screen.getByLabelText('Delete file');
      await user.click(deleteButton);

      expect(mockOnDeleteFile).toHaveBeenCalledWith('train.csv');
    });

    it('hides delete button when allowDelete is false', () => {
      render(<FileList files={[mockFile]} allowDelete={false} />);

      expect(screen.queryByLabelText('Delete file')).not.toBeInTheDocument();
    });

    it('does not render delete button for error items', () => {
      const errorItem: FileListError = { error: 'Error message' };

      render(<FileList files={[errorItem]} onDeleteFile={mockOnDeleteFile} />);

      expect(screen.queryByLabelText('Delete file')).not.toBeInTheDocument();
    });
  });

  describe('multiple files', () => {
    it('renders preview and delete buttons for each file', () => {
      const multipleFiles: FileListItem[] = [
        mockFile,
        { ...mockFile, path: 'test.csv' },
        { ...mockFile, path: 'validation.csv' },
      ];

      render(
        <FileList
          files={multipleFiles}
          onPreviewFile={mockOnPreviewFile}
          onDeleteFile={mockOnDeleteFile}
        />
      );

      expect(screen.getAllByLabelText('Preview file')).toHaveLength(3);
      expect(screen.getAllByLabelText('Delete file')).toHaveLength(3);
    });

    it('calls correct callback for specific file', async () => {
      const multipleFiles: FileListItem[] = [
        { ...mockFile, path: 'first.csv' },
        { ...mockFile, path: 'second.csv' },
      ];

      render(
        <FileList
          files={multipleFiles}
          onPreviewFile={mockOnPreviewFile}
          onDeleteFile={mockOnDeleteFile}
        />
      );

      const deleteButtons = screen.getAllByLabelText('Delete file');
      await user.click(deleteButtons[1]);

      expect(mockOnDeleteFile).toHaveBeenCalledWith('second.csv');
    });
  });

  describe('files without dataset', () => {
    it('renders files without dataset info (local uploads)', () => {
      const localFile: FileListItem = {
        path: 'uploaded.jsonl',
        url: 'blob:http://localhost/abc123',
        content: '{"example": 1}',
      };

      render(<FileList files={[localFile]} onPreviewFile={mockOnPreviewFile} />);

      expect(screen.getByText('uploaded.jsonl')).toBeInTheDocument();
    });
  });

  describe('combined props', () => {
    it('hides both buttons when both allow props are false', () => {
      render(<FileList files={[mockFile]} allowPreview={false} allowDelete={false} />);

      expect(screen.queryByLabelText('Preview file')).not.toBeInTheDocument();
      expect(screen.queryByLabelText('Delete file')).not.toBeInTheDocument();
    });

    it('shows preview only when allowDelete is false', () => {
      render(
        <FileList
          files={[mockFile]}
          allowPreview
          allowDelete={false}
          onPreviewFile={mockOnPreviewFile}
        />
      );

      expect(screen.getByLabelText('Preview file')).toBeInTheDocument();
      expect(screen.queryByLabelText('Delete file')).not.toBeInTheDocument();
    });

    it('shows delete only when allowPreview is false', () => {
      render(
        <FileList
          files={[mockFile]}
          allowPreview={false}
          allowDelete
          onDeleteFile={mockOnDeleteFile}
        />
      );

      expect(screen.queryByLabelText('Preview file')).not.toBeInTheDocument();
      expect(screen.getByLabelText('Delete file')).toBeInTheDocument();
    });
  });
});
