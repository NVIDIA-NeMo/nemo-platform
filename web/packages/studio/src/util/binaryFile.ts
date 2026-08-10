// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { BINARY_FILE_EXTENSIONS, IMAGE_FILE_EXTENSIONS } from '@studio/api/datasets/constants';

function getExtension(path: string): string | undefined {
  return path.split('.').at(-1)?.toLowerCase();
}

/** True when the file path has an extension in the known-binary blocklist. */
export function isBinaryExtension(path: string): boolean {
  const ext = getExtension(path);
  return ext !== undefined && BINARY_FILE_EXTENSIONS.has(ext);
}

/** True when the file path has an extension supported by the image preview. */
export function isImageExtension(path: string): boolean {
  const ext = getExtension(path);
  return ext !== undefined && IMAGE_FILE_EXTENSIONS.has(ext);
}
