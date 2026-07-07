import { PluginProvider, usePlugins } from '@studio/plugins/PluginContext';
import { renderHook, waitFor } from '@testing-library/react';

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

    const { result } = renderHook(() => usePlugins(), { wrapper: PluginProvider });

    // Wait for the fetch effect to settle so state updates happen inside act()
    await waitFor(() => {
      expect(result.current).toEqual([]);
    });
  });

  it('skips plugins with untrusted bundle URLs', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      json: async () => [{ name: 'evil', bundleUrl: 'https://evil.com/malicious.js' }],
    } as Response);

    const { result } = renderHook(() => usePlugins(), { wrapper: PluginProvider });

    // Wait for the effect to run — security gate rejects the URL before import()
    await waitFor(() => {
      expect(warnSpy).toHaveBeenCalledWith(
        expect.stringContaining('Rejected untrusted bundle URL')
      );
    });
    expect(result.current).toHaveLength(0);
    warnSpy.mockRestore();
  });

  it('warns when fetch fails', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.mocked(global.fetch).mockRejectedValue(new Error('network error'));

    const { result } = renderHook(() => usePlugins(), { wrapper: PluginProvider });

    await waitFor(() => {
      expect(warnSpy).toHaveBeenCalled();
    });
    expect(result.current).toHaveLength(0);
    warnSpy.mockRestore();
  });

  it('warns when response is not ok', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.mocked(global.fetch).mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => [],
    } as unknown as Response);

    const { result } = renderHook(() => usePlugins(), { wrapper: PluginProvider });

    await waitFor(() => {
      expect(warnSpy).toHaveBeenCalled();
    });
    expect(result.current).toHaveLength(0);
    warnSpy.mockRestore();
  });

  it('warns when /apis/plugins does not return an array', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      json: async () => ({ plugins: [] }), // object, not array
    } as unknown as Response);

    const { result } = renderHook(() => usePlugins(), { wrapper: PluginProvider });

    await waitFor(() => {
      expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('did not return an array'));
    });
    expect(result.current).toHaveLength(0);
    warnSpy.mockRestore();
  });

  it('skips a plugin with an untrusted bundle URL (missing-export path not unit-testable without dynamic-import mocking)', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    // The security gate rejects the URL before import() is called, so no
    // dynamic-import mock is needed here.  The branch in loadPlugin() that
    // checks for missing `mount`/`navItems` exports requires the ability to
    // mock dynamic import(), which Vitest does not yet support cleanly.
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      json: async () => [{ name: 'good', bundleUrl: 'https://evil.com/bad.js' }],
    } as unknown as Response);

    const { result } = renderHook(() => usePlugins(), { wrapper: PluginProvider });

    await waitFor(() => {
      expect(warnSpy).toHaveBeenCalledWith(
        expect.stringContaining('Rejected untrusted bundle URL')
      );
    });
    expect(result.current).toHaveLength(0);
    warnSpy.mockRestore();
  });
});
