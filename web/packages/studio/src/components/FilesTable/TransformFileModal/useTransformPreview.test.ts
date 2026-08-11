// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useTransformPreview } from '@studio/components/FilesTable/TransformFileModal/useTransformPreview';
import { act, renderHook } from '@testing-library/react';

const fileContent = JSON.stringify([{ name: 'Ada', role: 'engineer' }]);

describe('useTransformPreview', () => {
  it('applies mappings to nested keys', () => {
    const { result } = renderHook(() =>
      useTransformPreview({
        fileContent,
        fileType: 'json',
        mappings: [{ key: 'user.name', value: '{{name}}' }],
      })
    );

    expect(result.current.afterRow).toEqual({ user: { name: 'Ada' } });
  });

  it('does not throw when a later mapping nests under a key already set to a primitive', () => {
    const { result } = renderHook(() =>
      useTransformPreview({
        fileContent,
        fileType: 'json',
        mappings: [
          { key: 'user', value: '{{name}}' },
          { key: 'user.role', value: '{{role}}' },
        ],
      })
    );

    expect(result.current.afterRow).toEqual({ user: { role: 'engineer' } });
  });

  it('ignores mappings whose keys traverse the prototype chain', () => {
    const { result } = renderHook(() =>
      useTransformPreview({
        fileContent,
        fileType: 'json',
        mappings: [
          { key: '__proto__.polluted', value: 'yes' },
          { key: 'constructor', value: 'yes' },
          { key: 'user..name', value: '{{name}}' },
          { key: 'name', value: '{{name}}' },
        ],
      })
    );

    expect(result.current.afterRow).toEqual({ name: 'Ada' });
    expect(({} as Record<string, unknown>).polluted).toBeUndefined();
  });

  it('keeps rendering when a mapping holds an invalid template', () => {
    const { result } = renderHook(() =>
      useTransformPreview({
        fileContent,
        fileType: 'json',
        mappings: [
          { key: 'broken', value: '{{#if}}' },
          { key: 'name', value: '{{name}}' },
        ],
      })
    );

    expect(result.current.afterRow).toEqual({ broken: '{{#if}}', name: 'Ada' });
  });

  it('reports the row actually displayed when the row count shrinks', () => {
    const { result, rerender } = renderHook(
      (props: { fileContent: string }) =>
        useTransformPreview({
          fileContent: props.fileContent,
          fileType: 'json',
          mappings: [{ key: 'name', value: '{{name}}' }],
        }),
      {
        initialProps: {
          fileContent: JSON.stringify([{ name: 'Ada' }, { name: 'Grace' }, { name: 'Katherine' }]),
        },
      }
    );

    act(() => result.current.onRowChange(3));
    expect(result.current.currentRow).toBe(3);

    rerender({ fileContent: JSON.stringify([{ name: 'Ada' }]) });

    expect(result.current.currentRow).toBe(1);
    expect(result.current.totalRows).toBe(1);
  });
});
