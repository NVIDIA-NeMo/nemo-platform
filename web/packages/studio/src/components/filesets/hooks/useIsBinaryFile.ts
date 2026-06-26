// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KNOWN_TEXT_EXTENSIONS } from '@studio/constants/constants';
import { isBinaryExtension } from '@studio/util/binaryFile';

function isKnownTextExtension(path: string): boolean {
  const ext = path.split('.').at(-1)?.toLowerCase();
  return ext !== undefined && KNOWN_TEXT_EXTENSIONS.has(ext);
}

/**
 * Determine whether a fileset file should be treated as binary (no text preview).
 *
 * Strategy:
 *   - Extension in `KNOWN_TEXT_EXTENSIONS` → text immediately.
 *   - Extension in `BINARY_FILE_EXTENSIONS` → binary immediately.
 *   - Unknown extension → assume text (fail-open for preview).
 *
 * Returns `{ isBinary, isLoading }`. `isLoading` is always `false` since
 * detection is synchronous.
 */
export function useIsBinaryFile(filePath: string | undefined): {
  isBinary: boolean;
  isLoading: boolean;
} {
  if (!filePath) return { isBinary: false, isLoading: false };
  if (isKnownTextExtension(filePath)) return { isBinary: false, isLoading: false };
  if (isBinaryExtension(filePath)) return { isBinary: true, isLoading: false };
  return { isBinary: false, isLoading: false };
}
