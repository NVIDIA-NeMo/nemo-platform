// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DatasetFileDropzone } from '@studio/components/filesets/FilesetFileExplorer/DatasetFileDropzone';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock react-dropzone
const mockGetRootProps = vi.fn(() => ({}));
const mockGetInputProps = vi.fn(() => ({}));
const mockOpenFileDialog = vi.fn(() => {});
let mockIsDragActive = false;

vi.mock('react-dropzone', () => ({
  useDropzone: vi.fn(() => ({
    getRootProps: mockGetRootProps,
    getInputProps: mockGetInputProps,
    isDragActive: mockIsDragActive,
    open: mockOpenFileDialog,
  })),
}));

describe('DatasetFileDropzone', () => {
  const defaultProps = {
    datasetName: 'test-dataset',
    onUpload: vi.fn(),
    children: () => <div data-testid="child-content">Child Content</div>,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockIsDragActive = false;
  });

  it('renders children content', () => {
    render(<DatasetFileDropzone {...defaultProps} />);

    expect(screen.getByTestId('child-content')).toBeInTheDocument();
    expect(screen.getByText('Child Content')).toBeInTheDocument();
  });

  it('renders file input with correct attributes', () => {
    render(<DatasetFileDropzone {...defaultProps} />);

    const fileInput = screen.getByLabelText('Upload File');
    expect(fileInput).toBeInTheDocument();
    expect(fileInput).toHaveAttribute('data-testid', 'dataset-file-dropzone-input');
  });

  it('does not show drag overlay when not dragging', () => {
    mockIsDragActive = false;

    render(<DatasetFileDropzone {...defaultProps} />);

    expect(screen.queryByText(/Drop files into/)).not.toBeInTheDocument();
  });

  it('shows drag overlay when dragging files', () => {
    mockIsDragActive = true;

    render(<DatasetFileDropzone {...defaultProps} />);

    expect(screen.getByText(/Drop files into/)).toBeInTheDocument();
    expect(screen.getByText('test-dataset')).toBeInTheDocument();
    expect(screen.getByText(/choose the destination folder next/)).toBeInTheDocument();
  });
  it('opens file dialog when button is clicked', async () => {
    mockIsDragActive = true;

    render(
      <DatasetFileDropzone
        {...defaultProps}
        children={(openFileDialog: () => void) => (
          <button onClick={openFileDialog}>Upload File</button>
        )}
      />
    );

    const button = screen.getByText('Upload File');
    await userEvent.click(button);

    expect(mockOpenFileDialog).toHaveBeenCalled();
  });
});
