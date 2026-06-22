// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useDatasetFilesUpload } from '@studio/api/datasets/useDatasetFilesUpload';
import { useFileUpload } from '@studio/components/filesets/FilesetFileExplorer/hooks/useFileUpload';
import { renameFile } from '@studio/util/files';
import { renderHook } from '@testing-library/react';

vi.mock('@studio/api/datasets/useDatasetFilesUpload');
vi.mock('@studio/util/files');

describe('useFileUpload', () => {
  const mockMutateAsync = vi.fn();
  const mockUseDatasetFilesUpload = vi.mocked(useDatasetFilesUpload);
  const mockRenameFile = vi.mocked(renameFile);

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseDatasetFilesUpload.mockReturnValue({
      mutateAsync: mockMutateAsync,
      variables: undefined,
      isPending: false,
    } as unknown as ReturnType<typeof useDatasetFilesUpload>);
    mockRenameFile.mockImplementation((file, newName) => {
      return new File([file], newName, { type: file.type });
    });
  });

  it('should initialize with correct state', () => {
    const { result } = renderHook(() =>
      useFileUpload({
        workspace: 'test-workspace',
        datasetName: 'test-dataset',
        currentFolder: undefined,
      })
    );

    expect(result.current.isUploading).toBe(false);
    expect(result.current.pendingUploads).toBeUndefined();
    expect(typeof result.current.handleUpload).toBe('function');
  });

  it('should upload files without folder prefix when currentFolder is undefined', async () => {
    const { result } = renderHook(() =>
      useFileUpload({
        workspace: 'test-workspace',
        datasetName: 'test-dataset',
        currentFolder: undefined,
      })
    );

    const file1 = new File(['content1'], 'file1.txt', { type: 'text/plain' });
    const file2 = new File(['content2'], 'file2.txt', { type: 'text/plain' });

    mockMutateAsync.mockResolvedValue(undefined);

    await result.current.handleUpload([file1, file2]);

    expect(mockRenameFile).not.toHaveBeenCalled();
    expect(mockMutateAsync).toHaveBeenCalledWith({
      workspace: 'test-workspace',
      datasetName: 'test-dataset',
      files: [file1, file2],
    });
  });

  it('should prefix files with current folder when folder is provided', async () => {
    const { result } = renderHook(() =>
      useFileUpload({
        workspace: 'test-workspace',
        datasetName: 'test-dataset',
        currentFolder: 'training',
      })
    );

    const file1 = new File(['content1'], 'file1.txt', { type: 'text/plain' });
    const file2 = new File(['content2'], 'file2.txt', { type: 'text/plain' });

    mockMutateAsync.mockResolvedValue(undefined);

    await result.current.handleUpload([file1, file2]);

    expect(mockRenameFile).toHaveBeenCalledWith(file1, 'training/file1.txt');
    expect(mockRenameFile).toHaveBeenCalledWith(file2, 'training/file2.txt');
    expect(mockRenameFile).toHaveBeenCalledTimes(2);
  });

  it('should handle folder path with trailing slash correctly', async () => {
    const { result } = renderHook(() =>
      useFileUpload({
        workspace: 'test-workspace',
        datasetName: 'test-dataset',
        currentFolder: 'validation/',
      })
    );

    const file = new File(['content'], 'test.txt', { type: 'text/plain' });

    mockMutateAsync.mockResolvedValue(undefined);

    await result.current.handleUpload([file]);

    expect(mockRenameFile).toHaveBeenCalledWith(file, 'validation/test.txt');
  });

  it('should handle folder path without trailing slash correctly', async () => {
    const { result } = renderHook(() =>
      useFileUpload({
        workspace: 'test-workspace',
        datasetName: 'test-dataset',
        currentFolder: 'test',
      })
    );

    const file = new File(['content'], 'file.txt', { type: 'text/plain' });

    mockMutateAsync.mockResolvedValue(undefined);

    await result.current.handleUpload([file]);

    expect(mockRenameFile).toHaveBeenCalledWith(file, 'test/file.txt');
  });

  it('should expose isUploading state from mutation', () => {
    mockUseDatasetFilesUpload.mockReturnValue({
      mutateAsync: mockMutateAsync,
      variables: undefined,
      isPending: true,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);

    const { result } = renderHook(() =>
      useFileUpload({
        workspace: 'test-workspace',
        datasetName: 'test-dataset',
        currentFolder: undefined,
      })
    );

    expect(result.current.isUploading).toBe(true);
  });

  it('should expose pendingUploads from mutation variables', () => {
    const mockFiles = [new File(['test'], 'test.txt')];
    mockUseDatasetFilesUpload.mockReturnValue({
      mutateAsync: mockMutateAsync,
      variables: { files: mockFiles, workspace: 'test', datasetName: 'test' },
      isPending: true,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);

    const { result } = renderHook(() =>
      useFileUpload({
        workspace: 'test-workspace',
        datasetName: 'test-dataset',
        currentFolder: undefined,
      })
    );

    expect(result.current.pendingUploads).toEqual(mockFiles);
  });

  it('should handle empty file array', async () => {
    const { result } = renderHook(() =>
      useFileUpload({
        workspace: 'test-workspace',
        datasetName: 'test-dataset',
        currentFolder: 'folder',
      })
    );

    mockMutateAsync.mockResolvedValue(undefined);

    await result.current.handleUpload([]);

    expect(mockMutateAsync).not.toHaveBeenCalled();
  });

  it('should propagate upload errors', async () => {
    const { result } = renderHook(() =>
      useFileUpload({
        workspace: 'test-workspace',
        datasetName: 'test-dataset',
        currentFolder: undefined,
      })
    );

    const file = new File(['content'], 'file.txt', { type: 'text/plain' });
    const error = new Error('Upload failed');

    mockMutateAsync.mockRejectedValue(error);

    await expect(result.current.handleUpload([file])).rejects.toThrow('Upload failed');
  });

  it('should update handleUpload when dependencies change', () => {
    const { result, rerender } = renderHook((props) => useFileUpload(props), {
      initialProps: {
        workspace: 'test-workspace',
        datasetName: 'test-dataset',
        currentFolder: 'folder1',
      },
    });

    const firstHandleUpload = result.current.handleUpload;

    rerender({
      workspace: 'test-workspace',
      datasetName: 'test-dataset',
      currentFolder: 'folder2',
    });

    // handleUpload reference should change when currentFolder changes
    expect(result.current.handleUpload).not.toBe(firstHandleUpload);
  });

  it('should maintain stable handleUpload when dependencies do not change', () => {
    const { result, rerender } = renderHook(() =>
      useFileUpload({
        workspace: 'test-workspace',
        datasetName: 'test-dataset',
        currentFolder: 'folder',
      })
    );

    const firstHandleUpload = result.current.handleUpload;

    rerender();

    expect(result.current.handleUpload).toBe(firstHandleUpload);
  });

  it('should handle nested folder paths', async () => {
    const { result } = renderHook(() =>
      useFileUpload({
        workspace: 'test-workspace',
        datasetName: 'test-dataset',
        currentFolder: 'parent/child/grandchild',
      })
    );

    const file = new File(['content'], 'deep.txt', { type: 'text/plain' });

    mockMutateAsync.mockResolvedValue(undefined);

    await result.current.handleUpload([file]);

    expect(mockRenameFile).toHaveBeenCalledWith(file, 'parent/child/grandchild/deep.txt');
  });

  it('should use targetFolder argument over currentFolder when provided', async () => {
    const { result } = renderHook(() =>
      useFileUpload({
        workspace: 'test-workspace',
        datasetName: 'test-dataset',
        currentFolder: 'breadcrumb-folder',
      })
    );

    const file = new File(['content'], 'a.txt', { type: 'text/plain' });
    mockMutateAsync.mockResolvedValue(undefined);

    await result.current.handleUpload([file], 'picked-folder');

    expect(mockRenameFile).toHaveBeenCalledWith(file, 'picked-folder/a.txt');
  });
});
