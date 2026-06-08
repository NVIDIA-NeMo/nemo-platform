// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { BINARY_FILE_EXTENSIONS } from '@studio/api/datasets/constants';

/** True when the file path has an extension in the known-binary blocklist. */
export function isBinaryExtension(path: string): boolean {
  const ext = path.split('.').at(-1)?.toLowerCase();
  return ext !== undefined && BINARY_FILE_EXTENSIONS.has(ext);
}
