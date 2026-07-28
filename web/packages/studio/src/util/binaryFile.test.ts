// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { isImageExtension } from '@studio/util/binaryFile';

describe('isImageExtension', () => {
  it.each(['preview.png', 'preview.JPG', 'preview.svg', 'preview.webp'])(
    'recognizes browser-supported image format %s',
    (path) => {
      expect(isImageExtension(path)).toBe(true);
    }
  );

  it('does not classify other binary files as images', () => {
    expect(isImageExtension('archive.zip')).toBe(false);
  });
});
