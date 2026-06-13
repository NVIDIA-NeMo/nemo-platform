// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { InferenceProvidersDataView } from '@studio/components/dataViews/InferenceProvidersDataView';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { server } from '@studio/mocks/node';
import { renderRoute } from '@studio/tests/util/render';
import { waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';

vi.mock('use-debounce', () => ({
  useDebounce: (value: unknown) => [value, { cancel: () => {}, flush: () => {} }],
}));

const PROVIDERS_URL = `${PLATFORM_BASE_URL}/apis/models/v2/workspaces/:workspace/providers`;

const emptyProvidersPage = {
  data: [],
  pagination: {
    page: 1,
    page_size: 50,
    current_page_size: 0,
    total_pages: 0,
    total_results: 0,
  },
};

const captureRequests = () => {
  const requestUrls: string[] = [];
  server.use(
    http.get(PROVIDERS_URL, ({ request }) => {
      requestUrls.push(request.url);
      return HttpResponse.json(emptyProvidersPage);
    })
  );
  return requestUrls;
};

const renderDataView = (initialEntry: string) =>
  renderRoute(<InferenceProvidersDataView workspace="default" />, {
    history: initialEntry,
    routes: [
      {
        path: '/workspaces/:workspace/inference-providers',
        element: <InferenceProvidersDataView workspace="default" />,
      },
    ],
  });

describe('InferenceProvidersDataView', () => {
  afterEach(() => {
    server.resetHandlers();
  });

  it('sends no filter[ or search params on initial render', async () => {
    const requestUrls = captureRequests();
    renderDataView('/workspaces/default/inference-providers');

    await waitFor(() => expect(requestUrls.length).toBeGreaterThan(0));

    const keys = Array.from(new URL(requestUrls.at(-1)!).searchParams.keys());
    expect(keys.some((k) => k.startsWith('filter['))).toBe(false);
    expect(keys.some((k) => k === 'search' || k.startsWith('search['))).toBe(false);
  });

  it('sends filter[name][$like] when name search is active', async () => {
    const requestUrls = captureRequests();
    renderDataView('/workspaces/default/inference-providers?s=my-provider');

    await waitFor(() => {
      expect(requestUrls.some((u) => new URL(u).searchParams.has('filter[name][$like]'))).toBe(
        true
      );
    });

    const url = new URL(requestUrls.at(-1)!);
    expect(url.searchParams.get('filter[name][$like]')).toBe('my-provider');
    expect(url.searchParams.has('filter[name]')).toBe(false);
  });

  it('never emits a top-level search or search[ key', async () => {
    const requestUrls = captureRequests();
    renderDataView('/workspaces/default/inference-providers?s=foo');

    await waitFor(() => expect(requestUrls.length).toBeGreaterThan(0));

    for (const raw of requestUrls) {
      const params = new URL(raw).searchParams;
      expect(params.has('search')).toBe(false);
      expect(Array.from(params.keys()).some((k) => k.startsWith('search['))).toBe(false);
    }
  });
});
