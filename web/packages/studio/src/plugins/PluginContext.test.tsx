// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  usePluginInstalled,
  usePlugins,
  usePluginsError,
  usePluginsLoaded,
} from '@studio/plugins/PluginContext';
import { PluginProvider } from '@studio/plugins/PluginProvider';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';

const createWrapper = (retry: number | false = false) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry, retryDelay: 0 } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <PluginProvider>{children}</PluginProvider>
    </QueryClientProvider>
  );
};

const usePluginState = () => ({
  plugins: usePlugins(),
  isLoaded: usePluginsLoaded(),
  isError: usePluginsError(),
  agentsInstalled: usePluginInstalled('agents'),
});

beforeEach(() => {
  vi.resetAllMocks();
  global.fetch = vi.fn();
});

describe('PluginProvider', () => {
  it('starts with empty plugins', async () => {
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      json: async () => [],
    } as Response);

    const { result } = renderHook(usePluginState, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.isLoaded).toBe(true);
    });
    expect(result.current.plugins).toEqual([]);
    expect(result.current.isError).toBe(false);
  });

  it('skips plugins with untrusted bundle URLs', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      json: async () => [{ name: 'evil', bundleUrl: 'https://evil.com/malicious.js' }],
    } as Response);

    const { result } = renderHook(usePluginState, { wrapper: createWrapper() });

    // Wait for the query to settle — security gate rejects the URL before import()
    await waitFor(() => {
      expect(warnSpy).toHaveBeenCalledWith(
        expect.stringContaining('Rejected untrusted bundle URL')
      );
    });
    expect(result.current.plugins).toHaveLength(0);
    warnSpy.mockRestore();
  });

  it('exposes an error state when fetch fails', async () => {
    vi.mocked(global.fetch).mockRejectedValue(new Error('network error'));

    const { result } = renderHook(usePluginState, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.isLoaded).toBe(true);
    expect(result.current.plugins).toHaveLength(0);
  });

  it('exposes an error state when response is not ok', async () => {
    vi.mocked(global.fetch).mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => [],
    } as unknown as Response);

    const { result } = renderHook(usePluginState, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.isLoaded).toBe(true);
    expect(result.current.plugins).toHaveLength(0);
  });

  it('recovers when a transient fetch failure is retried', async () => {
    vi.mocked(global.fetch)
      .mockRejectedValueOnce(new Error('502 Bad Gateway'))
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [{ name: 'agents', bundleUrl: null }],
      } as Response);

    const { result } = renderHook(usePluginState, { wrapper: createWrapper(1) });

    await waitFor(() => {
      expect(result.current.isLoaded).toBe(true);
    });
    expect(result.current.isError).toBe(false);
    expect(result.current.agentsInstalled).toBe(true);
  });

  it('warns when /apis/plugins does not return an array', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      json: async () => ({ plugins: [] }), // object, not array
    } as unknown as Response);

    const { result } = renderHook(usePluginState, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('did not return an array'));
    });
    // Fails open: a malformed manifest surfaces as an error, not empty success.
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.plugins).toHaveLength(0);
    warnSpy.mockRestore();
  });
});
