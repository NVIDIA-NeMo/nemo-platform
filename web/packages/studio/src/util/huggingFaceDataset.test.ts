// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { CustomizationTemplateDataset } from '@studio/constants/customizationTemplates';
import { server } from '@studio/mocks/node';
import { fetchAndConvertDataset } from '@studio/util/huggingFaceDataset';
import { http, HttpResponse } from 'msw';

const HF_URL = 'https://datasets-server.huggingface.co/rows';

/** Responds with `length` identical rows so the converter has data to work with. */
const rowsHandler = (makeRow: () => Record<string, unknown> = () => ({ text: 'x' })) =>
  http.get(HF_URL, ({ request }) => {
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
  it('splits converted rows into training and validation JSONL blobs', async () => {
    server.use(rowsHandler(() => ({ text: 'hello' })));

    const { training, validation } = await fetchAndConvertDataset(dataset(), () => {});

    const trainingLines = (await training.text()).split('\n');
    const validationLines = (await validation.text()).split('\n');
    expect(trainingLines).toHaveLength(3);
    expect(validationLines).toHaveLength(2);
    expect(JSON.parse(trainingLines[0])).toEqual({ text: 'hello' });
  });

  it('reports progress up to the total requested row count', async () => {
    server.use(rowsHandler());
    const onProgress = vi.fn();

    await fetchAndConvertDataset(dataset(), onProgress);

    expect(onProgress).toHaveBeenLastCalledWith(5, 5);
  });

  it('paginates in 100-row pages for large datasets', async () => {
    let requests = 0;
    server.use(
      http.get(HF_URL, ({ request }) => {
        requests += 1;
        const length = Number(new URL(request.url).searchParams.get('length') ?? '0');
        return HttpResponse.json({ rows: Array.from({ length }, () => ({ row: { text: 'x' } })) });
      })
    );

    await fetchAndConvertDataset(
      dataset({ trainingRowCount: 150, validationRowCount: 50 }),
      () => {}
    );

    expect(requests).toBe(2); // 200 rows / 100 per page
  });

  it('throws when Hugging Face responds with an error', async () => {
    server.use(http.get(HF_URL, () => HttpResponse.json({ error: 'boom' }, { status: 500 })));

    await expect(fetchAndConvertDataset(dataset(), () => {})).rejects.toThrow(
      /Failed to fetch dataset from Hugging Face/
    );
  });

  it('throws when no rows survive conversion', async () => {
    server.use(rowsHandler());

    await expect(
      fetchAndConvertDataset(dataset({ convertRow: () => null }), () => {})
    ).rejects.toThrow(/Not enough valid training rows/);
  });

  it('throws when valid training rows are short of the configured count', async () => {
    // 2 valid rows for a 3-row training request — undersized but not empty.
    let served = 0;
    server.use(
      http.get(HF_URL, ({ request }) => {
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
    // Only enough valid rows to fill training, leaving validation empty.
    let served = 0;
    server.use(
      http.get(HF_URL, ({ request }) => {
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
      fetchAndConvertDataset(dataset({ convertRow: (row) => (row.drop ? null : row) }), () => {})
    ).rejects.toThrow(/Not enough valid validation rows/);
  });

  it('retries a transient failure and then succeeds', async () => {
    let calls = 0;
    server.use(
      http.get(HF_URL, ({ request }) => {
        calls += 1;
        if (calls === 1) return HttpResponse.json({ error: 'temporary' }, { status: 503 });
        const length = Number(new URL(request.url).searchParams.get('length') ?? '0');
        return HttpResponse.json({ rows: Array.from({ length }, () => ({ row: { text: 'x' } })) });
      })
    );

    const { training } = await fetchAndConvertDataset(dataset(), () => {});
    expect((await training.text()).split('\n')).toHaveLength(3);
    expect(calls).toBe(2); // one 503, one success
  });
});
