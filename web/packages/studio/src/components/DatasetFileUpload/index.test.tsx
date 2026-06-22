// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DatasetFileUpload } from '@studio/components/DatasetFileUpload';
import { mockFile, mockFile2, mockFile3 } from '@studio/mocks/studio-ui/files';
import { render, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';

describe('DatasetFileUpload', () => {
  const user = userEvent.setup();
  it('renders without error', () => {
    render(<DatasetFileUpload required accept={{ 'image/jpeg': ['.jpeg'] }} />);
    expect(screen.getByText('Drop a file or click to select a file')).toBeInTheDocument();
  });

  it('should handle file addition', async () => {
    const mockOnChange = vi.fn();
    render(
      <DatasetFileUpload required accept={{ 'image/jpeg': ['.jpeg'] }} onChange={mockOnChange} />
    );
    await user.upload(screen.getByTestId('dropzone'), mockFile3);
    expect(mockOnChange).toHaveBeenCalledWith(mockFile3);
  });

  it('should handle multiple file addition', async () => {
    const mockOnChange = vi.fn();
    const files = [mockFile, mockFile2];
    render(
      <DatasetFileUpload
        required
        multiple
        accept={{ 'text/plain': ['.txt'] }}
        onChange={mockOnChange}
      />
    );
    await user.upload(screen.getByTestId('dropzone'), files);
    expect(mockOnChange).toHaveBeenCalledWith(files);
  });

  it('should handle file removal', async () => {
    const mockOnChange = vi.fn();
    const files = [mockFile];

    render(
      <DatasetFileUpload
        required
        multiple
        accept={{ 'text/plain': ['.txt'] }}
        onChange={mockOnChange}
        files={files}
      />
    );
    await user.click(await screen.findByText(mockFile.name));
    expect(mockOnChange).toHaveBeenCalledWith([]);
  });
});
