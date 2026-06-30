// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DatasetFileSelect } from '@nemo/common/src/components/DatasetFileSelect/DatasetFileSelect';
import { suppressConsoleError } from '@nemo/testing/utils/suppress-console';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock the UploadModal component
vi.mock('@nemo/common/src/components/UploadModal', () => ({
  UploadModal: vi.fn(({ open, onClose, onSubmit, projectId }) => {
    if (!projectId) {
      console.error('UploadModal: projectId is required');
    }
    return open ? (
      <div data-testid="upload-modal">
        <button
          onClick={() =>
            onSubmit({
              type: 'dataset',
              dataset: {
                id: 'test-ns/test-dataset',
                name: 'test-dataset',
                workspace: 'test-ns',
                description: '',
                purpose: 'dataset',
                storage: { type: 'local', path: '/data' },
                metadata: {},
                custom_fields: {},
                project: 'default',
                created_at: '2024-01-01T00:00:00Z',
                updated_at: '2024-01-01T00:00:00Z',
              },
              path: 'test.csv',
              url: 'fileset://test-ns/test-dataset/test.csv',
            })
          }
        >
          Submit File
        </button>
        <button onClick={onClose}>Close Modal</button>
      </div>
    ) : null;
  }),
}));

// Mock the FileList component
vi.mock('@nemo/common/src/components/FileList', () => ({
  FileList: vi.fn(({ files, onDeleteFile }) => (
    <div data-testid="file-list">
      {files.map((file: { path: string }) => (
        <div key={file.path}>
          <span>{file.path}</span>
          <button onClick={() => onDeleteFile(file.path)}>Delete {file.path}</button>
        </div>
      ))}
    </div>
  )),
  FileListItem: vi.fn(),
}));

describe('DatasetFileSelect', () => {
  const user = userEvent.setup();
  const mockOnChange = vi.fn();
  const mockOnError = vi.fn();
  const mockOnClearError = vi.fn();
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    suppressConsoleError('UploadModal: projectId is required');
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
  });

  const renderWithClient = (ui: React.ReactElement) => {
    return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
  };

  describe('Initial State', () => {
    it('renders "Select File" button when no files are selected', () => {
      renderWithClient(<DatasetFileSelect workspace="test-project" onChange={mockOnChange} />);
      expect(screen.getByRole('button', { name: 'Select File' })).toBeInTheDocument();
    });

    it('does not render FileList when no files selected', () => {
      renderWithClient(<DatasetFileSelect workspace="test-project" onChange={mockOnChange} />);
      expect(screen.queryByTestId('file-list')).not.toBeInTheDocument();
    });
  });

  describe('With Selected File', () => {
    const mockValue = {
      dataset: {
        id: 'namespace/dataset-name',
        name: 'dataset-name',
        workspace: 'namespace',
        description: '',
        purpose: 'dataset' as const,
        storage: { type: 'local' as const, path: '/data' },
        metadata: {},
        custom_fields: {},
        project: 'default',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      },
      path: 'train.csv',
      url: 'fileset://namespace/dataset-name/train.csv',
    };

    it('renders dataset name when file is selected', () => {
      renderWithClient(
        <DatasetFileSelect workspace="test-project" value={mockValue} onChange={mockOnChange} />
      );
      expect(screen.getByText('dataset-name')).toBeInTheDocument();
    });

    it('renders "Change Dataset" button when file is selected', () => {
      renderWithClient(
        <DatasetFileSelect workspace="test-project" value={mockValue} onChange={mockOnChange} />
      );
      expect(screen.getByRole('button', { name: 'Change Dataset' })).toBeInTheDocument();
    });

    it('renders FileList component when file is selected', () => {
      renderWithClient(
        <DatasetFileSelect workspace="test-project" value={mockValue} onChange={mockOnChange} />
      );
      expect(screen.getByTestId('file-list')).toBeInTheDocument();
    });
  });

  describe('Modal Interaction', () => {
    it('opens modal when "Select File" button is clicked', async () => {
      renderWithClient(<DatasetFileSelect workspace="test-project" onChange={mockOnChange} />);

      const selectButton = screen.getByRole('button', { name: 'Select File' });
      await user.click(selectButton);

      await waitFor(() => {
        expect(screen.getByTestId('upload-modal')).toBeInTheDocument();
      });
    });

    it('opens modal when "Change Dataset" button is clicked', async () => {
      const mockValue = {
        dataset: {
          id: 'namespace/dataset',
          name: 'dataset',
          workspace: 'namespace',
          description: '',
          purpose: 'dataset' as const,
          storage: { type: 'local' as const, path: '/data' },
          metadata: {},
          custom_fields: {},
          project: 'default',
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
        path: 'train.csv',
        url: 'fileset://namespace/dataset/train.csv',
      };

      renderWithClient(
        <DatasetFileSelect workspace="test-project" value={mockValue} onChange={mockOnChange} />
      );

      const changeButton = screen.getByRole('button', { name: 'Change Dataset' });
      await user.click(changeButton);

      await waitFor(() => {
        expect(screen.getByTestId('upload-modal')).toBeInTheDocument();
      });
    });

    it('closes modal and calls onChange when file is submitted', async () => {
      renderWithClient(<DatasetFileSelect workspace="test-project" onChange={mockOnChange} />);

      // Open modal
      const selectButton = screen.getByRole('button', { name: 'Select File' });
      await user.click(selectButton);

      // Submit file
      const submitButton = screen.getByText('Submit File');
      await user.click(submitButton);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith([
          expect.objectContaining({
            dataset: expect.objectContaining({
              workspace: 'test-ns',
              name: 'test-dataset',
            }),
            path: 'test.csv',
            url: 'fileset://test-ns/test-dataset/test.csv',
          }),
        ]);
      });
      expect(screen.queryByTestId('upload-modal')).not.toBeInTheDocument();
    });
  });

  describe('File Type Validation', () => {
    it('validates accepted file types and shows error for invalid files', async () => {
      renderWithClient(
        <DatasetFileSelect
          workspace="test-project"
          acceptedFileTypes={['.jsonl']}
          onChange={mockOnChange}
          onError={mockOnError}
        />
      );

      // Open modal
      const selectButton = screen.getByRole('button', { name: 'Select File' });
      await user.click(selectButton);

      // Submit CSV file (invalid)
      const submitButton = screen.getByText('Submit File');
      await user.click(submitButton);

      await waitFor(() => {
        expect(mockOnError).toHaveBeenCalledWith({
          message: 'Invalid file type(s) (.csv). Accepted types: .jsonl. Invalid files: test.csv',
          filepath: 'test.csv',
        });
      });
      expect(mockOnChange).not.toHaveBeenCalled();
      expect(screen.queryByTestId('upload-modal')).not.toBeInTheDocument();
    });

    it('accepts valid file types', async () => {
      renderWithClient(
        <DatasetFileSelect
          workspace="test-project"
          acceptedFileTypes={['.csv']}
          onChange={mockOnChange}
          onClearError={mockOnClearError}
        />
      );

      // Open modal
      const selectButton = screen.getByRole('button', { name: 'Select File' });
      await user.click(selectButton);

      // Submit CSV file (valid)
      const submitButton = screen.getByText('Submit File');
      await user.click(submitButton);

      await waitFor(() => expect(mockOnChange).toHaveBeenCalled());
      expect(mockOnClearError).toHaveBeenCalled();
    });

    it('allows all file types when acceptedFileTypes is not provided', async () => {
      renderWithClient(
        <DatasetFileSelect
          workspace="test-project"
          onChange={mockOnChange}
          onClearError={mockOnClearError}
        />
      );

      // Open modal
      const selectButton = screen.getByRole('button', { name: 'Select File' });
      await user.click(selectButton);

      // Submit file
      const submitButton = screen.getByText('Submit File');
      await user.click(submitButton);

      await waitFor(() => expect(mockOnChange).toHaveBeenCalled());
      expect(mockOnClearError).toHaveBeenCalled();
    });
  });

  describe('File Deletion', () => {
    it('calls onChange with null when file is deleted', async () => {
      const mockValue = {
        dataset: {
          id: 'namespace/dataset',
          name: 'dataset',
          workspace: 'namespace',
          description: '',
          purpose: 'dataset' as const,
          storage: { type: 'local' as const, path: '/data' },
          metadata: {},
          custom_fields: {},
          project: 'default',
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
        path: 'train.csv',
        url: 'fileset://namespace/dataset/train.csv',
      };

      renderWithClient(
        <DatasetFileSelect
          workspace="test-project"
          value={mockValue}
          onChange={mockOnChange}
          onClearError={mockOnClearError}
        />
      );

      const deleteButton = screen.getByText('Delete train.csv');
      await user.click(deleteButton);

      expect(mockOnChange).toHaveBeenCalledWith([]);
      expect(mockOnClearError).toHaveBeenCalled();
    });
  });

  describe('Error Display', () => {
    it('displays error text when errorText prop is provided', () => {
      const mockValue = {
        dataset: {
          id: 'namespace/dataset',
          name: 'dataset',
          workspace: 'namespace',
          description: '',
          purpose: 'dataset' as const,
          storage: { type: 'local' as const, path: '/data' },
          metadata: {},
          custom_fields: {},
          project: 'default',
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
        path: 'train.csv',
        url: 'fileset://namespace/dataset/train.csv',
      };
      const errorMessage = 'Test error message';

      renderWithClient(
        <DatasetFileSelect
          workspace="test-project"
          value={mockValue}
          errorText={errorMessage}
          onChange={mockOnChange}
        />
      );

      expect(screen.getByText(errorMessage)).toBeInTheDocument();
    });
  });

  describe('Split Information Props', () => {
    it('passes split information props to FileList', () => {
      const mockValue = {
        dataset: {
          id: 'namespace/dataset',
          name: 'dataset',
          workspace: 'namespace',
          description: '',
          purpose: 'dataset' as const,
          storage: { type: 'local' as const, path: '/data' },
          metadata: {},
          custom_fields: {},
          project: 'default',
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
        path: 'train.csv',
        url: 'fileset://namespace/dataset/train.csv',
      };

      renderWithClient(
        <DatasetFileSelect
          workspace="test-project"
          value={mockValue}
          showSplitInformation
          holdoutSplitPercentage={20}
          onChange={mockOnChange}
        />
      );

      expect(screen.getByTestId('file-list')).toBeInTheDocument();
    });
  });

  describe('Dataset Handling', () => {
    it('handles dataset with namespace and name', async () => {
      renderWithClient(<DatasetFileSelect workspace="test-project" onChange={mockOnChange} />);

      const selectButton = screen.getByRole('button', { name: 'Select File' });
      await user.click(selectButton);

      const submitButton = screen.getByText('Submit File');
      await user.click(submitButton);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith([
          expect.objectContaining({
            dataset: expect.objectContaining({
              workspace: 'test-ns',
              name: 'test-dataset',
            }),
          }),
        ]);
      });
    });

    it('displays only dataset name (without workspace) in the UI', () => {
      const mockValue = {
        dataset: {
          id: 'my-workspace/my-dataset',
          name: 'my-dataset',
          workspace: 'my-workspace',
          description: '',
          purpose: 'dataset' as const,
          storage: { type: 'local' as const, path: '/data' },
          metadata: {},
          custom_fields: {},
          project: 'default',
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
        path: 'train.csv',
        url: 'fileset://my-workspace/my-dataset/train.csv',
      };

      renderWithClient(
        <DatasetFileSelect workspace="test-project" value={mockValue} onChange={mockOnChange} />
      );
      expect(screen.getByText('my-dataset')).toBeInTheDocument();
      expect(screen.queryByText('my-workspace')).not.toBeInTheDocument();
    });
  });

  describe('Render text content', () => {
    it('renders error text', () => {
      renderWithClient(
        <DatasetFileSelect
          workspace="test-project"
          errorText="Test Error"
          onChange={mockOnChange}
        />
      );
      expect(screen.getByText('Test Error')).toBeInTheDocument();
    });
  });
});
