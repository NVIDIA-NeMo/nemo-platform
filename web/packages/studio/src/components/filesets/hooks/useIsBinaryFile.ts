// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Importing from the SDK fetchers module activates the Axios interceptor that
// injects the OIDC Bearer token, so axios.head() calls below are auth-aware.
import '@nemo/sdk/generated/fetchers/platform';
import { getFilesDownloadFileQueryKey } from '@nemo/sdk/generated/platform/api';
import { isBinaryExtension } from '@studio/util/binaryFile';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';

/**
 * Extensions that are unambiguously text. The backend HEAD endpoint returns
 * `application/octet-stream` for all files, so Content-Type-based detection
 * fails for these. This allowlist short-circuits the HEAD request.
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
 * Strategy (four tiers):
 *   1. Extension in `KNOWN_TEXT_EXTENSIONS` → text immediately, no network.
 *   2. Extension in `BINARY_FILE_EXTENSIONS` → binary immediately, no network.
 *   3. Extension not in either list → HEAD request; `Content-Type` decides.
 *      - `text/*` or known text application types → not binary.
 *      - Everything else → binary.
 *   4. HEAD fails / no Content-Type → assume text (fail-open for preview).
 *
 * Returns `{ isBinary, isLoading }`. `isLoading` is true only during the HEAD
 * request (tier-3 path); tiers 1-2 resolve synchronously.
 */
export function useIsBinaryFile(
  workspace: string,
  filesetName: string,
  filePath: string | undefined
): { isBinary: boolean; isLoading: boolean } {
  const knownText = filePath !== undefined && isKnownTextExtension(filePath);
  const blocklisted = filePath !== undefined && isBinaryExtension(filePath);

  const { data: headBinary, isPending } = useQuery({
    queryKey: ['file-content-type', workspace, filesetName, filePath],
    queryFn: async (): Promise<boolean> => {
      try {
        // axios.head() is auth-aware via the interceptor registered when
        // '@nemo/sdk/generated/fetchers/platform' is imported above.
        const [fileUrl] = getFilesDownloadFileQueryKey(
          encodeURIComponent(workspace),
          encodeURIComponent(filesetName),
          encodeURIComponent(filePath!)
        );
        const res = await axios.head(fileUrl);
        const ct = String(res.headers['content-type'] ?? '');
        return !isTextContentType(ct);
      } catch {
        return false; // fail-open: assume text
      }
    },
    enabled: !!filePath && !knownText && !blocklisted,
    staleTime: Infinity,
    retry: false,
  });

  if (!filePath) return { isBinary: false, isLoading: false };
  if (knownText) return { isBinary: false, isLoading: false };
  if (blocklisted) return { isBinary: true, isLoading: false };
  return { isBinary: headBinary ?? false, isLoading: isPending };
}

const TEXT_CONTENT_TYPES = [
  'text/',
  'application/json',
  'application/xml',
  'application/javascript',
  'application/typescript',
  'application/yaml',
  'application/x-yaml',
  'application/toml',
  'application/csv',
  'application/x-sh',
];

function isTextContentType(ct: string): boolean {
  // Extract the MIME type token only (strip "; charset=..." parameters) before
  // matching, so parameter values can't accidentally trigger a false positive.
  const mimeToken = ct.split(';')[0].trim().toLowerCase();
  return TEXT_CONTENT_TYPES.some((prefix) => mimeToken.startsWith(prefix));
}
