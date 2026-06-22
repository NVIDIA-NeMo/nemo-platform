// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { triggerDownload } from '@nemo/common/src/utils/file';
import { useBulkDownload } from '@studio/components/filesets/hooks/useBulkDownload';
import { useDownloadFileAsArrayBuffer } from '@studio/components/filesets/hooks/useDownloadFileAsArrayBuffer';
import type { FileSystemFile } from '@studio/components/FilesTable/utils';
import { act, renderHook, waitFor } from '@testing-library/react';

vi.mock('@nemo/common/src/providers/toast/useToast');
vi.mock('@nemo/common/src/utils/file');
vi.mock('@studio/components/filesets/hooks/useDownloadFileAsArrayBuffer');

const mockUseToast = vi.mocked(useToast);
const mockTriggerDownload = vi.mocked(triggerDownload);
const mockUseDownloadFileAsArrayBuffer = vi.mocked(useDownloadFileAsArrayBuffer);

const workspace = 'ws';
const datasetName = 'ds';

const file = (path: string): FileSystemFile => ({
  type: 'file',
  path,
  size: 1,
  oid: path,
});

describe('useBulkDownload', () => {
  const workingWithId = vi.fn();
  const dismissToast = vi.fn();
  const success = vi.fn();
  const error = vi.fn();
  const downloadAsArrayBuffer = vi.fn();
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    workingWithId.mockReturnValue('toast-id');

    mockUseToast.mockReturnValue({
      workingWithId,
      dismissToast,
      success,
      error,
      info: vi.fn(),
      warning: vi.fn(),
    } as unknown as ReturnType<typeof useToast>);

    mockUseDownloadFileAsArrayBuffer.mockReturnValue(downloadAsArrayBuffer);
    downloadAsArrayBuffer.mockResolvedValue(new ArrayBuffer(8));

    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  const render = () => renderHook(() => useBulkDownload({ workspace, datasetName }));

  it('is a no-op for an empty array and does not show a toast', async () => {
    const { result } = render();

    await act(async () => {
      await result.current.handleBulkDownload([]);
    });

    expect(workingWithId).not.toHaveBeenCalled();
    expect(downloadAsArrayBuffer).not.toHaveBeenCalled();
    expect(mockTriggerDownload).not.toHaveBeenCalled();
  });

  it('triggers a browser save per file and shows the singular success toast', async () => {
    const { result } = render();

    await act(async () => {
      await result.current.handleBulkDownload([file('data/a.txt')]);
    });

    expect(workingWithId).toHaveBeenCalledWith('Downloading file...');
    expect(mockTriggerDownload).toHaveBeenCalledTimes(1);
    expect(mockTriggerDownload).toHaveBeenCalledWith(expect.any(ArrayBuffer), 'a.txt');
    expect(success).toHaveBeenCalledWith('Successfully downloaded file!');
  });

  it('uses a plural working + success toast for multi-file batches', async () => {
    const { result } = render();

    await act(async () => {
      await result.current.handleBulkDownload([file('a.txt'), file('b.txt')]);
    });

    expect(workingWithId).toHaveBeenCalledWith('Downloading 2 files...');
    expect(mockTriggerDownload).toHaveBeenCalledTimes(2);
    expect(success).toHaveBeenCalledWith('Successfully downloaded 2 files!');
  });

  it('reports a partial-success toast when some downloads fail', async () => {
    downloadAsArrayBuffer.mockResolvedValueOnce(new ArrayBuffer(4)).mockResolvedValueOnce(null);

    const { result } = render();

    await act(async () => {
      await result.current.handleBulkDownload([file('a.txt'), file('b.txt')]);
    });

    // Only the successful buffer should have triggered a save.
    expect(mockTriggerDownload).toHaveBeenCalledTimes(1);
    expect(error).toHaveBeenCalledWith('Downloaded 1 of 2 files. 1 failed.');
    expect(success).not.toHaveBeenCalled();
  });

  it('reports a total-failure toast when every download fails', async () => {
    downloadAsArrayBuffer.mockResolvedValue(null);

    const { result } = render();

    await act(async () => {
      await result.current.handleBulkDownload([file('a.txt'), file('b.txt')]);
    });

    expect(mockTriggerDownload).not.toHaveBeenCalled();
    expect(error).toHaveBeenCalledWith('Unable to download files. Please try again later.');
  });

  it('dismisses the working toast and surfaces an error toast when a download throws', async () => {
    const boom = new Error('worker exploded');
    downloadAsArrayBuffer.mockRejectedValue(boom);

    const { result } = render();

    await act(async () => {
      await result.current.handleBulkDownload([file('a.txt')]);
    });

    expect(consoleErrorSpy).toHaveBeenCalledWith('Bulk download failed', boom);
    expect(dismissToast).toHaveBeenCalledWith('toast-id');
    expect(error).toHaveBeenCalledWith('Failed to download file');
    expect(success).not.toHaveBeenCalled();
    expect(mockTriggerDownload).not.toHaveBeenCalled();
    expect(result.current.isDownloading).toBe(false);
  });

  it('uses plural error copy for multi-file batches that throw', async () => {
    downloadAsArrayBuffer.mockRejectedValue(new Error('boom'));

    const { result } = render();

    await act(async () => {
      await result.current.handleBulkDownload([file('a.txt'), file('b.txt')]);
    });

    expect(error).toHaveBeenCalledWith('Failed to download files');
  });

  it('keeps isDownloading true for the full batch', async () => {
    let resolveDownload: (value: ArrayBuffer | null) => void = () => {};
    downloadAsArrayBuffer.mockReturnValue(
      new Promise((res) => {
        resolveDownload = res;
      })
    );

    const { result } = render();

    expect(result.current.isDownloading).toBe(false);

    let pending: Promise<void> | undefined;
    act(() => {
      pending = result.current.handleBulkDownload([file('a.txt')]);
    });

    await waitFor(() => expect(result.current.isDownloading).toBe(true));

    await act(async () => {
      resolveDownload(new ArrayBuffer(1));
      await pending;
    });
    expect(result.current.isDownloading).toBe(false);
  });
});
