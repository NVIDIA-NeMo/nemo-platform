// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useTransformPreview } from '@studio/components/transform/useTransformPreview';
import { act, renderHook } from '@testing-library/react';

const fileContent = JSON.stringify([{ name: 'Ada', role: 'engineer' }]);

describe('useTransformPreview', () => {
  it('renders the template against the current row, keeping its shape', () => {
    const { result } = renderHook(() =>
      useTransformPreview({
        fileContent,
        fileType: 'json',
        template: { user: { name: '{{ name }}' }, messages: [{ content: '{{ role }}' }] },
      })
    );

    expect(result.current.afterRow).toEqual({
      user: { name: 'Ada' },
      messages: [{ content: 'engineer' }],
    });
  });

  it('has no output until the template writes a key', () => {
    const { result } = renderHook(() =>
      useTransformPreview({ fileContent, fileType: 'json', template: {} })
    );

    expect(result.current.sourceRow).toEqual({ name: 'Ada', role: 'engineer' });
    expect(result.current.afterRow).toBeNull();
  });

  it('keeps rendering when one value holds an invalid template', () => {
    const { result } = renderHook(() =>
      useTransformPreview({
        fileContent,
        fileType: 'json',
        template: { broken: '{{#if}}', name: '{{ name }}' },
      })
    );

    expect(result.current.afterRow).toEqual({ broken: '{{#if}}', name: 'Ada' });
    expect(result.current.approximated).toBe(true);
  });

  it('reports the row actually displayed when the row count shrinks', () => {
    const { result, rerender } = renderHook(
      (props: { fileContent: string }) =>
        useTransformPreview({
          fileContent: props.fileContent,
          fileType: 'json',
          template: { name: '{{ name }}' },
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
