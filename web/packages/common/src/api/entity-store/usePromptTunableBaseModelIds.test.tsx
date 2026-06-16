// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { modelsListModels } from '@nemo/sdk/generated/platform/api';
import type { ModelEntity, ModelEntitysPage } from '@nemo/sdk/generated/platform/schema';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';

import { usePromptTunableBaseModelIds } from './usePromptTunableBaseModelIds';
import { DEFAULT_NAMESPACE } from '../../constants';

vi.mock('@nemo/sdk/generated/platform/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@nemo/sdk/generated/platform/api')>();
  return {
    ...actual,
    modelsListModels: vi.fn(),
  };
});

const mockModelsListModels = vi.mocked(modelsListModels);

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

const makeModel = (id: string, overrides: Partial<ModelEntity> = {}): ModelEntity =>
  ({
    id,
    name: id,
    workspace: 'ws1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }) as ModelEntity;

const makePage = (data: ModelEntity[], page: number, totalPages: number): ModelEntitysPage => ({
  data,
  pagination: {
    page,
    page_size: 50,
    current_page_size: data.length,
    total_pages: totalPages,
    total_results: data.length * totalPages,
  },
});

describe('usePromptTunableBaseModelIds', () => {
  beforeEach(() => {
    mockModelsListModels.mockReset();
  });

  it('returns ids from both workspace and default namespace queries', async () => {
    mockModelsListModels.mockImplementation(async (workspace) => {
      if (workspace === 'ws1') return makePage([makeModel('id-ws-1')], 1, 1);
      if (workspace === DEFAULT_NAMESPACE) return makePage([makeModel('id-default-1')], 1, 1);
      return makePage([], 1, 1);
    });

    const { result } = renderHook(() => usePromptTunableBaseModelIds({ workspace: 'ws1' }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.promptTunableIds).toEqual(new Set(['id-ws-1', 'id-default-1']));
  });

  it('sends filter: { lora_enabled: true } and no other filter keys', async () => {
    mockModelsListModels.mockResolvedValue(makePage([], 1, 1));

    renderHook(() => usePromptTunableBaseModelIds({ workspace: 'ws1' }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(mockModelsListModels).toHaveBeenCalled());

    for (const call of mockModelsListModels.mock.calls) {
      const params = call[1];
      expect(params?.filter).toEqual({ lora_enabled: true });
    }
  });

  it('skips the default-namespace query when workspace === DEFAULT_NAMESPACE', async () => {
    mockModelsListModels.mockResolvedValue(makePage([makeModel('id-default-1')], 1, 1));

    const { result } = renderHook(
      () => usePromptTunableBaseModelIds({ workspace: DEFAULT_NAMESPACE }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(mockModelsListModels).toHaveBeenCalledTimes(1);
    expect(mockModelsListModels).toHaveBeenCalledWith(DEFAULT_NAMESPACE, expect.anything());
    expect(result.current.promptTunableIds).toEqual(new Set(['id-default-1']));
  });

  it('auto-fetches subsequent pages until total_pages is reached', async () => {
    const wsPages = [
      makePage([makeModel('ws-1'), makeModel('ws-2')], 1, 2),
      makePage([makeModel('ws-3')], 2, 2),
    ];
    let wsCall = 0;

    mockModelsListModels.mockImplementation(async (workspace) => {
      if (workspace === 'ws1') return wsPages[wsCall++] ?? makePage([], 2, 2);
      return makePage([], 1, 1);
    });

    const { result } = renderHook(() => usePromptTunableBaseModelIds({ workspace: 'ws1' }), {
      wrapper: createWrapper(),
    });

    await waitFor(
      () => expect(result.current.promptTunableIds).toEqual(new Set(['ws-1', 'ws-2', 'ws-3'])),
      { timeout: 5000 }
    );

    expect(result.current.isLoading).toBe(false);
  });

  it('filters out non-base entities via isBaseModel', async () => {
    const adapter = {
      ...makeModel('adapter-1'),
      base_model: { name: 'llama', namespace: 'meta' },
    } as unknown as ModelEntity;

    mockModelsListModels.mockImplementation(async (workspace) => {
      if (workspace === 'ws1') return makePage([makeModel('base-1'), adapter], 1, 1);
      return makePage([], 1, 1);
    });

    const { result } = renderHook(() => usePromptTunableBaseModelIds({ workspace: 'ws1' }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.promptTunableIds).toEqual(new Set(['base-1']));
  });

  it('reports isLoading=true during initial load and false after both queries settle', async () => {
    let resolveWs: (page: ModelEntitysPage) => void = () => {};
    let resolveDefault: (page: ModelEntitysPage) => void = () => {};

    mockModelsListModels.mockImplementation((workspace) => {
      if (workspace === 'ws1') return new Promise<ModelEntitysPage>((r) => (resolveWs = r));
      return new Promise<ModelEntitysPage>((r) => (resolveDefault = r));
    });

    const { result } = renderHook(() => usePromptTunableBaseModelIds({ workspace: 'ws1' }), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(true);

    resolveWs(makePage([makeModel('ws-1')], 1, 1));
    // Workspace settled, but default query is still pending — keep loading.
    await waitFor(() => expect(result.current.promptTunableIds.has('ws-1')).toBe(true));
    expect(result.current.isLoading).toBe(true);

    resolveDefault(makePage([makeModel('default-1')], 1, 1));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.promptTunableIds).toEqual(new Set(['ws-1', 'default-1']));
  });
});
