// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { HF_DATASETS_API } from '@studio/api/datasets/huggingFaceRows';
import { useHuggingFaceDatasetRows } from '@studio/api/datasets/useHuggingFaceDatasetRows';
import { server } from '@studio/mocks/node';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';

const SOURCE = { hfDataset: 'owner/ds', hfConfig: 'default', hfSplit: 'train' };

/** Serves rows whose `index` is their absolute position, so page ordering is assertable. */
const indexedRowsHandler = (onRequest?: () => void) =>
  http.get(HF_DATASETS_API, ({ request }) => {
    onRequest?.();
    const params = new URL(request.url).searchParams;
    const offset = Number(params.get('offset') ?? '0');
    const length = Number(params.get('length') ?? '0');
    return HttpResponse.json({
      rows: Array.from({ length }, (_, i) => ({ row: { index: offset + i } })),
    });
  });

describe('useHuggingFaceDatasetRows', () => {
  it('paginates a large read and flattens the pages in split order', async () => {
    let requests = 0;
    server.use(
      indexedRowsHandler(() => {
        requests += 1;
      })
    );

    const { result } = renderHook(
      () => useHuggingFaceDatasetRows({ source: SOURCE, rowCount: 150 }),
      { wrapper: TestProviders }
    );

    await waitFor(() => expect(result.current.rows).toBeDefined());

    expect(requests).toBe(2);
    expect(result.current.rows).toHaveLength(150);
    expect(result.current.rows?.[0]).toEqual({ index: 0 });
    expect(result.current.rows?.[99]).toEqual({ index: 99 });
    expect(result.current.rows?.[100]).toEqual({ index: 100 });
    expect(result.current.rows?.[149]).toEqual({ index: 149 });
    expect(result.current.isError).toBe(false);
  });

  it('does not fetch while disabled', async () => {
    let requests = 0;
    server.use(
      indexedRowsHandler(() => {
        requests += 1;
      })
    );

    const { result } = renderHook(
      () => useHuggingFaceDatasetRows({ source: SOURCE, rowCount: 50, enabled: false }),
      { wrapper: TestProviders }
    );

    // Give any in-flight request a chance to land before asserting none was made.
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(requests).toBe(0);
    expect(result.current.rows).toBeUndefined();
    // A disabled hook is idle, not loading — a caller gating a spinner on this must not spin.
    expect(result.current.isFetching).toBe(false);
  });

  it('surfaces the error when a page fails, without retrying a non-transient status', async () => {
    let attempts = 0;
    server.use(
      http.get(HF_DATASETS_API, () => {
        attempts += 1;
        return HttpResponse.json({ error: 'nope' }, { status: 400 });
      })
    );

    const { result } = renderHook(
      () => useHuggingFaceDatasetRows({ source: SOURCE, rowCount: 10 }),
      {
        wrapper: TestProviders,
      }
    );

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(attempts).toBe(1);
    expect(result.current.rows).toBeUndefined();
    expect(result.current.error?.message).toMatch(/Failed to fetch dataset from Hugging Face/);
  });

  it('errors on a 200 whose payload is not a rows page, without retrying', async () => {
    let attempts = 0;
    server.use(
      http.get(HF_DATASETS_API, () => {
        attempts += 1;
        return HttpResponse.json({});
      })
    );

    const { result } = renderHook(
      () => useHuggingFaceDatasetRows({ source: SOURCE, rowCount: 10 }),
      {
        wrapper: TestProviders,
      }
    );

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(attempts).toBe(1);
    expect(result.current.rows).toBeUndefined();
  });

  it('retries a transient status up to the configured budget, then gives up', async () => {
    let attempts = 0;
    server.use(
      http.get(HF_DATASETS_API, () => {
        attempts += 1;
        return HttpResponse.json({ error: 'flaky' }, { status: 503 });
      })
    );

    const { result } = renderHook(
      () => useHuggingFaceDatasetRows({ source: SOURCE, rowCount: 10 }),
      {
        wrapper: TestProviders,
      }
    );

    await waitFor(() => expect(result.current.isError).toBe(true), { timeout: 5_000 });

    expect(attempts).toBe(3);
  });
});
