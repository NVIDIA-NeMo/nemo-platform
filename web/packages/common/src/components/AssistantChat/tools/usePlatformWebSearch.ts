// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  setWebSearchProvider,
  type WebSearchProvider,
} from '@nemo/common/src/components/AssistantChat/tools/webSearch';
import { PLATFORM_BASE_URL } from '@nemo/common/src/constants/environment';
import { useEffect, useRef } from 'react';
import { useAuth } from 'react-oidc-context';

const WEB_SEARCH_PATH = '/apis/studio/v1/web-search';

const buildUrl = (): string => {
  if (typeof window !== 'undefined' && !PLATFORM_BASE_URL) {
    return WEB_SEARCH_PATH;
  }
  try {
    return new URL(WEB_SEARCH_PATH, PLATFORM_BASE_URL).toString();
  } catch {
    return WEB_SEARCH_PATH;
  }
};

/**
 * Install a `WebSearchProvider` that calls the Studio service's `/v1/web-search`
 * endpoint with the user's bearer token. Mount once at the chat boundary; the
 * provider is uninstalled (reverting to the stub) on unmount.
 */
export const useInstallPlatformWebSearchProvider = (enabled: boolean): void => {
  const auth = useAuth();
  const accessTokenRef = useRef<string | undefined>(auth?.user?.access_token);
  accessTokenRef.current = auth?.user?.access_token;

  useEffect(() => {
    if (!enabled) return;
    const url = buildUrl();
    const provider: WebSearchProvider = {
      search: async ({ query, maxResults }, { signal }) => {
        const headers: Record<string, string> = {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        };
        const token = accessTokenRef.current;
        if (token) headers.Authorization = `Bearer ${token}`;

        let response: Response;
        try {
          response = await fetch(url, {
            method: 'POST',
            headers,
            body: JSON.stringify({ query, max_results: maxResults }),
            signal,
          });
        } catch (error: unknown) {
          // fetch() throws TypeError for network-level failures: CORS, mixed content,
          // wrong origin, missing route on the platform, server not running, etc.
          if (error instanceof DOMException && error.name === 'AbortError') throw error;
          throw new Error(
            `Could not reach the web search endpoint at ${url}. ` +
              'Check that the platform is running and was restarted after web_search ' +
              'was added (the route is mounted at /apis/studio/v1/web-search), and that ' +
              'the studio dev origin can talk to PLATFORM_BASE_URL.'
          );
        }

        if (!response.ok) {
          const body = await response.text().catch(() => '');
          const detail = body.slice(0, 200).trim();
          throw new Error(
            `Web search returned ${response.status} ${response.statusText}${detail ? `: ${detail}` : ''}`.trim()
          );
        }
        return response.json();
      },
    };

    setWebSearchProvider(provider);
    return () => setWebSearchProvider(null);
  }, [enabled]);
};
