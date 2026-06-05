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
 * Determine whether a fileset file should be treated as binary (no text preview).
 *
 * Strategy (three tiers):
 *   1. Extension in `BINARY_FILE_EXTENSIONS` → binary immediately, no network.
 *   2. Extension not in blocklist → HEAD request; `Content-Type` header decides.
 *      - `text/*` or known text application types → not binary.
 *      - Everything else → binary.
 *   3. HEAD fails / no Content-Type → assume text (fail-open for preview).
 *
 * Returns `{ isBinary, isLoading }`. `isLoading` is true only during the HEAD
 * request (tier-2 path); tier-1 resolves synchronously.
 */
export function useIsBinaryFile(
  workspace: string,
  filesetName: string,
  filePath: string | undefined
): { isBinary: boolean; isLoading: boolean } {
  const blocklisted = filePath !== undefined && isBinaryExtension(filePath);

  const { data: headBinary, isPending } = useQuery({
    queryKey: ['file-content-type', workspace, filesetName, filePath],
    queryFn: async (): Promise<boolean> => {
      if (!filePath) return false;
      try {
        // axios.head() is auth-aware via the interceptor registered when
        // '@nemo/sdk/generated/fetchers/platform' is imported above.
        const [fileUrl] = getFilesDownloadFileQueryKey(
          encodeURIComponent(workspace),
          encodeURIComponent(filesetName),
          encodeURIComponent(filePath)
        );
        const res = await axios.head(fileUrl);
        const ct = String(res.headers['content-type'] ?? '');
        return !isTextContentType(ct);
      } catch {
        return false; // fail-open: assume text
      }
    },
    enabled: !!filePath && !blocklisted,
    staleTime: Infinity,
    retry: false,
  });

  if (blocklisted) return { isBinary: true, isLoading: false };
  if (!filePath) return { isBinary: false, isLoading: false };
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
