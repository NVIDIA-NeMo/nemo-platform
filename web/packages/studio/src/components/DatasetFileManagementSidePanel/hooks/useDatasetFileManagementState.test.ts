// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useDatasetFileManagementState } from '@studio/components/DatasetFileManagementSidePanel/hooks/useDatasetFileManagementState';
import { act, renderHook } from '@testing-library/react';

describe('useDatasetFileManagementState', () => {
  it('should initialize with closed state and no folder', () => {
    const { result } = renderHook(() => useDatasetFileManagementState());

    expect(result.current.isOpen).toBe(false);
    expect(result.current.currentFolder).toBeUndefined();
  });

  it('should open sidepanel in specific folder', () => {
    const { result } = renderHook(() => useDatasetFileManagementState());

    act(() => {
      result.current.openInFolder('training/');
    });

    expect(result.current.isOpen).toBe(true);
    expect(result.current.currentFolder).toBe('training/');
  });

  it('should close sidepanel', () => {
    const { result } = renderHook(() => useDatasetFileManagementState());

    act(() => {
      result.current.openInFolder('training/');
    });

    expect(result.current.isOpen).toBe(true);

    act(() => {
      result.current.close();
    });

    expect(result.current.isOpen).toBe(false);
    // Folder should remain set even after closing
    expect(result.current.currentFolder).toBe('training/');
  });

  it('should change folder without closing', () => {
    const { result } = renderHook(() => useDatasetFileManagementState());

    act(() => {
      result.current.openInFolder('training/');
    });

    expect(result.current.currentFolder).toBe('training/');

    act(() => {
      result.current.setFolder('validation/');
    });

    expect(result.current.isOpen).toBe(true);
    expect(result.current.currentFolder).toBe('validation/');
  });

  it('should handle multiple open/close cycles', () => {
    const { result } = renderHook(() => useDatasetFileManagementState());

    // First cycle
    act(() => {
      result.current.openInFolder('training/');
    });
    expect(result.current.isOpen).toBe(true);
    expect(result.current.currentFolder).toBe('training/');

    act(() => {
      result.current.close();
    });
    expect(result.current.isOpen).toBe(false);

    // Second cycle with different folder
    act(() => {
      result.current.openInFolder('validation/');
    });
    expect(result.current.isOpen).toBe(true);
    expect(result.current.currentFolder).toBe('validation/');
  });

  it('should update folder while sidepanel is closed', () => {
    const { result } = renderHook(() => useDatasetFileManagementState());

    act(() => {
      result.current.setFolder('training/');
    });

    expect(result.current.isOpen).toBe(false);
    expect(result.current.currentFolder).toBe('training/');
  });

  it('should maintain stable function references', () => {
    const { result, rerender } = renderHook(() => useDatasetFileManagementState());

    const { openInFolder, close, setFolder } = result.current;

    rerender();

    expect(result.current.openInFolder).toBe(openInFolder);
    expect(result.current.close).toBe(close);
    expect(result.current.setFolder).toBe(setFolder);
  });
});
