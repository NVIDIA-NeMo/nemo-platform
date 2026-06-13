// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { UploadModal } from '@nemo/common/src/components/UploadModal/index';
import { suppressConsoleError } from '@nemo/testing/utils/suppress-console';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock validation
vi.mock('@nemo/common/src/components/UploadModal/validation', () => ({
  validateUploadForm: vi.fn(),
}));

// Mock child components for simpler testing
vi.mock('@nemo/common/src/components/UploadModal/DatasetUploader/index', () => ({
  DatasetUploader: () => <div data-testid="dataset-uploader">DatasetUploader Component</div>,
}));

vi.mock('@nemo/common/src/components/UploadModal/FileUpload', () => ({
  FileUpload: () => <div data-testid="file-upload">FileUpload Component</div>,
}));

vi.mock('@nemo/common/src/components/UploadModal/SimpleFilesTable', () => ({
  SimpleFilesTable: () => <div data-testid="files-table">SimpleFilesTable Component</div>,
}));

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

describe('UploadModal', () => {
  const user = userEvent.setup();
  const mockOnSubmit = vi.fn();
  const mockOnClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    suppressConsoleError('UploadModal: workspace is required');
  });

  it('renders modal with title', () => {
    render(
      <UploadModal
        workspace="test-project"
        open
        onSubmit={mockOnSubmit}
        onClose={mockOnClose}
        title="Test Modal"
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText('Test Modal')).toBeInTheDocument();
  });

  it('does not render when open is false', () => {
    render(
      <UploadModal
        workspace="test-project"
        open={false}
        onSubmit={mockOnSubmit}
        onClose={mockOnClose}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.queryByRole('heading', { name: 'Select a File' })).not.toBeInTheDocument();
  });

  it('returns null when projectId is not provided', () => {
    render(<UploadModal workspace="" open onSubmit={mockOnSubmit} onClose={mockOnClose} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders file upload by default when includeDataset is false', () => {
    render(
      <UploadModal workspace="test-project" open onSubmit={mockOnSubmit} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByTestId('file-upload')).toBeInTheDocument();
  });

  it('renders dataset uploader when includeDataset is true', () => {
    render(
      <UploadModal
        workspace="test-project"
        open
        includeDataset
        onSubmit={mockOnSubmit}
        onClose={mockOnClose}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByTestId('dataset-uploader')).toBeInTheDocument();
  });

  it('renders tabs when includeTabs is true', () => {
    render(
      <UploadModal
        workspace="test-project"
        open
        includeTabs
        onSubmit={mockOnSubmit}
        onClose={mockOnClose}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByRole('tab', { name: 'Select from Dataset' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Upload a File' })).toBeInTheDocument();
  });

  it('renders submit and cancel buttons with custom text', () => {
    render(
      <UploadModal
        workspace="test-project"
        open
        onSubmit={mockOnSubmit}
        onClose={mockOnClose}
        submitButtonText="Submit"
        cancelButtonText="Cancel"
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText('Submit')).toBeInTheDocument();
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });

  it('calls onClose when cancel button is clicked', async () => {
    render(
      <UploadModal
        workspace="test-project"
        open
        onSubmit={mockOnSubmit}
        onClose={mockOnClose}
        cancelButtonText="Cancel"
      />,
      { wrapper: createWrapper() }
    );

    const cancelButton = screen.getByText('Cancel');
    await user.click(cancelButton);

    expect(mockOnClose).toHaveBeenCalled();
  });

  it('renders with UploadModalProvider for context', () => {
    render(
      <UploadModal workspace="test-project" open onSubmit={mockOnSubmit} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    // Modal should render successfully with provider wrapper
    expect(screen.getByText('Select a File')).toBeInTheDocument();
  });

  it('switches between tabs when includeTabs is enabled', async () => {
    render(
      <UploadModal
        workspace="test-project"
        open
        includeTabs
        onSubmit={mockOnSubmit}
        onClose={mockOnClose}
      />,
      { wrapper: createWrapper() }
    );

    // Initially on dataset tab
    expect(screen.getByTestId('dataset-uploader')).toBeInTheDocument();

    // Switch to file tab
    const fileTab = screen.getByRole('tab', { name: 'Upload a File' });
    await user.click(fileTab);

    expect(screen.getByTestId('file-upload')).toBeInTheDocument();
  });
});
