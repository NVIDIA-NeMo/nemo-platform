// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { HF_DATASETS_API } from '@studio/api/datasets/huggingFaceRows';
import type { CustomizationTemplateDataset } from '@studio/constants/customizationTemplates';
import { server } from '@studio/mocks/node';
import { fetchAndConvertDataset } from '@studio/util/huggingFaceDataset';
import { QueryClient } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';

const rowsHandler = (makeRow: () => Record<string, unknown> = () => ({ text: 'x' })) =>
  http.get(HF_DATASETS_API, ({ request }) => {
    const length = Number(new URL(request.url).searchParams.get('length') ?? '0');
    return HttpResponse.json({ rows: Array.from({ length }, () => ({ row: makeRow() })) });
  });

const dataset = (
  overrides: Partial<CustomizationTemplateDataset> = {}
): CustomizationTemplateDataset => ({
  hfDataset: 'owner/ds',
  hfConfig: 'default',
  hfSplit: 'train',
  trainingRowCount: 3,
  validationRowCount: 2,
  name: 'test-dataset',
  convertRow: (row) => row,
  ...overrides,
});

describe('fetchAndConvertDataset', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient();
  });

  it('splits converted rows into training and validation JSONL blobs', async () => {
    server.use(rowsHandler(() => ({ text: 'hello' })));

    const { training, validation } = await fetchAndConvertDataset(queryClient, dataset(), () => {});

    const trainingLines = (await training.text()).split('\n');
    const validationLines = (await validation.text()).split('\n');
    expect(trainingLines).toHaveLength(3);
    expect(validationLines).toHaveLength(2);
    expect(JSON.parse(trainingLines[0])).toEqual({ text: 'hello' });
  });

  it('reports progress up to the total requested row count', async () => {
    server.use(rowsHandler());
    const onProgress = vi.fn();

    await fetchAndConvertDataset(queryClient, dataset(), onProgress);

    expect(onProgress).toHaveBeenLastCalledWith(5, 5);
  });

  it('does not backfill a dropped training row from the validation partition', async () => {
    server.use(
      http.get(HF_DATASETS_API, () =>
        HttpResponse.json({
          rows: [
            { row: { text: 'a' } },
            { row: { drop: true } },
            { row: { text: 'c' } },
            { row: { text: 'd' } },
            { row: { text: 'e' } },
          ],
        })
      )
    );

    await expect(
      fetchAndConvertDataset(
        queryClient,
        dataset({
          trainingRowCount: 3,
          validationRowCount: 2,
          convertRow: (row) => (row.drop ? null : row),
        }),
        () => {}
      )
    ).rejects.toThrow(/Not enough valid training rows: needed 3, found 2/);
  });

  it('paginates in 100-row pages for large datasets', async () => {
    let requests = 0;
    server.use(
      http.get(HF_DATASETS_API, ({ request }) => {
        requests += 1;
        const length = Number(new URL(request.url).searchParams.get('length') ?? '0');
        return HttpResponse.json({ rows: Array.from({ length }, () => ({ row: { text: 'x' } })) });
      })
    );

    await fetchAndConvertDataset(
      queryClient,
      dataset({ trainingRowCount: 150, validationRowCount: 50 }),
      () => {}
    );

    expect(requests).toBe(2);
  });

  it('throws when Hugging Face responds with an error', async () => {
    server.use(
      http.get(HF_DATASETS_API, () => HttpResponse.json({ error: 'boom' }, { status: 500 }))
    );

    await expect(fetchAndConvertDataset(queryClient, dataset(), () => {})).rejects.toThrow(
      /Failed to fetch dataset from Hugging Face/
    );
  });

  it.each([
    ['null', null],
    ['undefined', undefined],
    ['a string', 'not-a-row'],
    ['an array', [1, 2]],
  ])('throws when a 200 carries %s in place of a row object', async (_label, row) => {
    server.use(http.get(HF_DATASETS_API, () => HttpResponse.json({ rows: [{ row }] })));

    await expect(fetchAndConvertDataset(queryClient, dataset(), () => {})).rejects.toThrow(
      /unexpected response shape/
    );
  });

  it('throws when no rows survive conversion', async () => {
    server.use(rowsHandler());

    await expect(
      fetchAndConvertDataset(queryClient, dataset({ convertRow: () => null }), () => {})
    ).rejects.toThrow(/Not enough valid training rows/);
  });

  it('throws when valid training rows are short of the configured count', async () => {
    let served = 0;
    server.use(
      http.get(HF_DATASETS_API, ({ request }) => {
        const length = Number(new URL(request.url).searchParams.get('length') ?? '0');
        const rows = Array.from({ length }, () => {
          const valid = served < 2;
          served += 1;
          return { row: valid ? { text: 'x' } : { drop: true } };
        });
        return HttpResponse.json({ rows });
      })
    );

    await expect(
      fetchAndConvertDataset(
        queryClient,
        dataset({
          trainingRowCount: 3,
          validationRowCount: 0,
          convertRow: (row) => (row.drop ? null : row),
        }),
        () => {}
      )
    ).rejects.toThrow(/Not enough valid training rows: needed 3, found 2/);
  });

  it('throws when validation is requested but yields no rows', async () => {
    let served = 0;
    server.use(
      http.get(HF_DATASETS_API, ({ request }) => {
        const length = Number(new URL(request.url).searchParams.get('length') ?? '0');
        const rows = Array.from({ length }, () => {
          const valid = served < 3;
          served += 1;
          return { row: valid ? { text: 'x' } : { drop: true } };
        });
        return HttpResponse.json({ rows });
      })
    );

    await expect(
      fetchAndConvertDataset(
        queryClient,
        dataset({ convertRow: (row) => (row.drop ? null : row) }),
        () => {}
      )
    ).rejects.toThrow(/Not enough valid validation rows/);
  });

  it('retries a transient failure and then succeeds', async () => {
    let calls = 0;
    server.use(
      http.get(HF_DATASETS_API, ({ request }) => {
        calls += 1;
        if (calls === 1) return HttpResponse.json({ error: 'temporary' }, { status: 503 });
        const length = Number(new URL(request.url).searchParams.get('length') ?? '0');
        return HttpResponse.json({ rows: Array.from({ length }, () => ({ row: { text: 'x' } })) });
      })
    );

    const { training } = await fetchAndConvertDataset(queryClient, dataset(), () => {});
    expect((await training.text()).split('\n')).toHaveLength(3);
    expect(calls).toBe(2);
  });
});
