// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useIsBinaryFile } from '@studio/components/filesets/hooks/useIsBinaryFile';
import { renderHook } from '@testing-library/react';

describe('useIsBinaryFile', () => {
  it('returns isBinary=false for .jsonl files', () => {
    const { result } = renderHook(() =>
      useIsBinaryFile('default', 'test-dataset', 'data/test.jsonl')
    );

    expect(result.current).toEqual({ isBinary: false, isLoading: false });
  });

  it('returns isBinary=false for .json files', () => {
    const { result } = renderHook(() => useIsBinaryFile('default', 'test-dataset', 'config.json'));

    expect(result.current).toEqual({ isBinary: false, isLoading: false });
  });

  it('returns isBinary=false for .csv files', () => {
    const { result } = renderHook(() => useIsBinaryFile('default', 'test-dataset', 'data.csv'));

    expect(result.current).toEqual({ isBinary: false, isLoading: false });
  });

  it('returns isBinary=false for .py files', () => {
    const { result } = renderHook(() => useIsBinaryFile('default', 'test-dataset', 'script.py'));

    expect(result.current).toEqual({ isBinary: false, isLoading: false });
  });

  it('returns isBinary=false for .yaml and .yml files', () => {
    const { result } = renderHook(() => useIsBinaryFile('default', 'test-dataset', 'config.yaml'));

    expect(result.current).toEqual({ isBinary: false, isLoading: false });
  });

  it('returns isBinary=false for .md files', () => {
    const { result } = renderHook(() => useIsBinaryFile('default', 'test-dataset', 'README.md'));

    expect(result.current).toEqual({ isBinary: false, isLoading: false });
  });

  it('returns isBinary=false when filePath is undefined', () => {
    const { result } = renderHook(() => useIsBinaryFile('default', 'test-dataset', undefined));

    expect(result.current).toEqual({ isBinary: false, isLoading: false });
  });

  it('returns isBinary=true for .png files (binary blocklist)', () => {
    const { result } = renderHook(() => useIsBinaryFile('default', 'test-dataset', 'image.png'));

    expect(result.current).toEqual({ isBinary: true, isLoading: false });
  });

  it('returns isBinary=true for .zip files (binary blocklist)', () => {
    const { result } = renderHook(() => useIsBinaryFile('default', 'test-dataset', 'archive.zip'));

    expect(result.current).toEqual({ isBinary: true, isLoading: false });
  });

  it('returns isBinary=false for unknown extensions (fail-open)', () => {
    const { result } = renderHook(() => useIsBinaryFile('default', 'test-dataset', 'data.unknown'));

    expect(result.current).toEqual({ isBinary: false, isLoading: false });
  });
});
