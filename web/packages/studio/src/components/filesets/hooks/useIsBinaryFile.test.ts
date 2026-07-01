// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useIsBinaryFile } from '@studio/components/filesets/hooks/useIsBinaryFile';
import { renderHook } from '@testing-library/react';

describe('useIsBinaryFile', () => {
  it('returns isBinary=false for .jsonl files', () => {
    const { result } = renderHook(() => useIsBinaryFile('data/test.jsonl'));

    expect(result.current).toEqual({ isBinary: false, isLoading: false });
  });

  it('returns isBinary=false for .json files', () => {
    const { result } = renderHook(() => useIsBinaryFile('config.json'));

    expect(result.current).toEqual({ isBinary: false, isLoading: false });
  });

  it('returns isBinary=false for .csv files', () => {
    const { result } = renderHook(() => useIsBinaryFile('data.csv'));

    expect(result.current).toEqual({ isBinary: false, isLoading: false });
  });

  it('returns isBinary=false for .py files', () => {
    const { result } = renderHook(() => useIsBinaryFile('script.py'));

    expect(result.current).toEqual({ isBinary: false, isLoading: false });
  });

  it('returns isBinary=false for .yaml and .yml files', () => {
    const { result: yamlResult } = renderHook(() => useIsBinaryFile('config.yaml'));
    const { result: ymlResult } = renderHook(() => useIsBinaryFile('config.yml'));

    expect(yamlResult.current).toEqual({ isBinary: false, isLoading: false });
    expect(ymlResult.current).toEqual({ isBinary: false, isLoading: false });
  });

  it('returns isBinary=false for .md files', () => {
    const { result } = renderHook(() => useIsBinaryFile('README.md'));

    expect(result.current).toEqual({ isBinary: false, isLoading: false });
  });

  it('returns isBinary=false when filePath is undefined', () => {
    const { result } = renderHook(() => useIsBinaryFile(undefined));

    expect(result.current).toEqual({ isBinary: false, isLoading: false });
  });

  it('returns isBinary=true for .png files (binary blocklist)', () => {
    const { result } = renderHook(() => useIsBinaryFile('image.png'));

    expect(result.current).toEqual({ isBinary: true, isLoading: false });
  });

  it('returns isBinary=true for .zip files (binary blocklist)', () => {
    const { result } = renderHook(() => useIsBinaryFile('archive.zip'));

    expect(result.current).toEqual({ isBinary: true, isLoading: false });
  });

  it('returns isBinary=false for unknown extensions (fail-open)', () => {
    const { result } = renderHook(() => useIsBinaryFile('data.unknown'));

    expect(result.current).toEqual({ isBinary: false, isLoading: false });
  });
});
