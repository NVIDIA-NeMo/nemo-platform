// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useTransformPreview } from '@studio/components/FilesTable/TransformFileModal/useTransformPreview';
import { renderHook } from '@testing-library/react';

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
});
