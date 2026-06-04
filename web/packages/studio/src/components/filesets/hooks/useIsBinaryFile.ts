// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { BINARY_FILE_EXTENSIONS } from '@studio/api/datasets/constants';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from 'react-oidc-context';

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
  const auth = useAuth();

  const ext = filePath?.split('.').at(-1)?.toLowerCase();
  const blocklisted = ext !== undefined && BINARY_FILE_EXTENSIONS.has(ext);

  const { data: headBinary, isPending } = useQuery({
    queryKey: ['file-content-type', workspace, filesetName, filePath],
    queryFn: async (): Promise<boolean> => {
      if (!filePath) return false;
      const url = [
        PLATFORM_BASE_URL,
        '/apis/files/v2/workspaces/',
        encodeURIComponent(workspace),
        '/filesets/',
        encodeURIComponent(filesetName),
        '/-/',
        encodeURIComponent(filePath),
      ].join('');
      try {
        const res = await fetch(url, {
          method: 'HEAD',
          headers: auth.user?.access_token
            ? { Authorization: `Bearer ${auth.user.access_token}` }
            : {},
        });
        const ct = res.headers.get('content-type') ?? '';
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
  const lower = ct.toLowerCase();
  return TEXT_CONTENT_TYPES.some((prefix) => lower.includes(prefix));
}
