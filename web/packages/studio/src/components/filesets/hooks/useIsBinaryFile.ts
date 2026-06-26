// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { isBinaryExtension } from '@studio/util/binaryFile';

/**
 * Extensions that are unambiguously text. The backend always returns
 * `application/octet-stream` for all files, so Content-Type-based detection
 * is unusable — this allowlist is the authority for text classification.
 */
const KNOWN_TEXT_EXTENSIONS = new Set([
  // Data
  'json',
  'jsonl',
  'csv',
  'tsv',
  // Code
  'py',
  'js',
  'jsx',
  'ts',
  'tsx',
  'java',
  'c',
  'cpp',
  'h',
  'go',
  'rs',
  'rb',
  'php',
  'swift',
  'kt',
  'scala',
  'r',
  'm',
  'sh',
  'bash',
  'zsh',
  'fish',
  // Markup / Config
  'html',
  'htm',
  'xml',
  'yaml',
  'yml',
  'toml',
  'ini',
  'cfg',
  'conf',
  'jsonc',
  'env',
  // Text
  'txt',
  'md',
  'rst',
  'log',
  'diff',
  'patch',
  // Other
  'sql',
  'graphql',
  'proto',
  'dockerfile',
  'makefile',
]);

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
export function useIsBinaryFile(
  _workspace: string,
  _filesetName: string,
  filePath: string | undefined
): { isBinary: boolean; isLoading: boolean } {
  if (!filePath) return { isBinary: false, isLoading: false };
  if (isKnownTextExtension(filePath)) return { isBinary: false, isLoading: false };
  if (isBinaryExtension(filePath)) return { isBinary: true, isLoading: false };
  return { isBinary: false, isLoading: false };
}
