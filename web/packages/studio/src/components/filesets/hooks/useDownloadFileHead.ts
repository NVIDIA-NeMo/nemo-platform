// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { useCallback } from 'react';
import { useAuth } from 'react-oidc-context';

export interface DownloadFileHeadArgs {
  workspace: string;
  datasetName: string;
  path: string;
  /** Number of bytes to fetch. Defaults to 65536 (64 KB). */
  bytes?: number;
}

/**
 * Returns a callback that fetches the first N bytes of a fileset file via an
 * HTTP Range request. Useful for schema inference or content sniffing without
 * downloading large files in full.
 *
 * Resolves to `null` on any transport or HTTP error.
 */
export function useDownloadFileHead() {
  const auth = useAuth();

  return useCallback(
    async ({
      workspace,
      datasetName,
      path,
      bytes = 65536,
    }: DownloadFileHeadArgs): Promise<ArrayBuffer | null> => {
      const url = [
        PLATFORM_BASE_URL,
        '/apis/files/v2/workspaces/',
        encodeURIComponent(workspace),
        '/filesets/',
        encodeURIComponent(datasetName),
        '/-/',
        encodeURIComponent(path),
      ].join('');

      const headers: Record<string, string> = {
        Range: `bytes=0-${bytes - 1}`,
      };
      if (auth.user?.access_token) {
        headers.Authorization = `Bearer ${auth.user.access_token}`;
      }

      try {
        const res = await fetch(url, { headers });
        // 200 (server ignores range) and 206 (partial content) are both usable.
        if (!res.ok && res.status !== 206) return null;
        return res.arrayBuffer();
      } catch {
        return null;
      }
    },
    [auth.user?.access_token]
  );
}
