// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { modelsListModels } from '@nemo/sdk/generated/platform/api';
import type { ModelEntity, ModelEntitysPage } from '@nemo/sdk/generated/platform/schema';
import type { FilesetTemplate } from '@studio/components/CreateFilesetStart/types';
import { useJobBuilder } from '@studio/routes/DataDesignerJobBuildRoute/useJobBuilder';
import { renderHook, waitFor } from '@testing-library/react';
import { StrictMode } from 'react';

vi.mock('@nemo/sdk/generated/platform/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@nemo/sdk/generated/platform/api')>();
  return { ...actual, modelsListModels: vi.fn() };
});

const mockListModels = vi.mocked(modelsListModels);

const NEMOTRON = 'nvidia-llama-3-3-nemotron-super-49b-v1';

const makePage = (data: ModelEntity[]): ModelEntitysPage =>
  ({ data, pagination: { page: 1, total_pages: 1 } }) as ModelEntitysPage;

const model = (name: string, providers: string[] = ['ws1/build']): ModelEntity =>
  ({ id: name, name, workspace: 'ws1', model_providers: providers }) as unknown as ModelEntity;

/** A template that seeds a bare model name, the way the real templates do. */
const template = {
  id: 'text-to-python',
  models: [{ alias: 'default', model: NEMOTRON }],
  columns: [],
} as unknown as FilesetTemplate;

beforeEach(() => {
  mockListModels.mockReset();
  mockListModels.mockResolvedValue(makePage([model(NEMOTRON), model('some-other-model')]));
});

describe('useJobBuilder template auto-fill', () => {
  it('applies under StrictMode, where effects mount twice', async () => {
    const { result } = renderHook(() => useJobBuilder(template, 'ws1'), { wrapper: StrictMode });

    await waitFor(() =>
      expect(result.current.getBuilderValues().models[0]).toMatchObject({
        model: `ws1/${NEMOTRON}`,
        provider: 'ws1/build',
      })
    );
  });

  it('resolves each seeded model exactly once', async () => {
    const { result } = renderHook(() => useJobBuilder(template, 'ws1'), { wrapper: StrictMode });

    await waitFor(() =>
      expect(result.current.getBuilderValues().models[0].provider).toBe('ws1/build')
    );

    // One preferred-name lookup plus one first-page fallback, for the single seeded model.
    expect(mockListModels).toHaveBeenCalledTimes(2);
  });

  it('clears the model when the workspace has nothing to resolve to', async () => {
    mockListModels.mockResolvedValue(makePage([]));

    const { result } = renderHook(() => useJobBuilder(template, 'ws1'), { wrapper: StrictMode });

    await waitFor(() => expect(result.current.getBuilderValues().models[0].model).toBe(''));
  });

  it('leaves models that already carry a provider alone', async () => {
    const seeded = {
      ...template,
      models: [{ alias: 'default', model: NEMOTRON }],
    } as unknown as FilesetTemplate;

    const { result } = renderHook(
      () => useJobBuilder(seeded, 'ws1', { name: 'clone', rows: '10', columns: [], models: [] }),
      { wrapper: StrictMode }
    );

    await waitFor(() => expect(result.current.getBuilderValues().models).toEqual([]));
    expect(mockListModels).not.toHaveBeenCalled();
  });
});
