// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { usePlugins, usePluginsLoaded } from '@studio/plugins/PluginContext';
import { PluginRenderer } from '@studio/plugins/PluginRenderer';
import type { LoadedPlugin, PluginRootProps } from '@studio/plugins/types';
import { render, screen } from '@testing-library/react';
import { useEffect } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const authState = vi.hoisted(() => ({ accessToken: 'test-token' }));

let capturedProps: PluginRootProps | undefined;
const mountSpy = vi.fn();
const mockNavItems = vi.fn(() => []);

function MockRoot(props: PluginRootProps) {
  capturedProps = props;
  useEffect(() => {
    mountSpy();
  }, []);
  return (
    <div data-testid="plugin-root">
      ws:{props.host.workspaceId} token:{props.host.auth.accessToken}
    </div>
  );
}

function makePlugin(name: string): LoadedPlugin {
  return { name, Root: MockRoot, navItems: mockNavItems };
}

vi.mock('@studio/plugins/PluginContext', () => ({
  usePlugins: vi.fn(),
  usePluginsLoaded: vi.fn(),
}));
vi.mock('react-oidc-context', () => ({
  useAuth: vi.fn(() => ({ user: { access_token: authState.accessToken } })),
}));

vi.mock('@studio/hooks/useWorkspaceFromPath', () => ({
  useWorkspaceFromPath: vi.fn(() => 'my-workspace'),
}));

function renderPlugin(pluginName = 'test-plugin') {
  return render(
    <MemoryRouter initialEntries={[`/workspaces/ws1/plugin/${pluginName}/`]}>
      <Routes>
        <Route path="/workspaces/:workspace/plugin/:pluginName/*" element={<PluginRenderer />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  authState.accessToken = 'test-token';
  capturedProps = undefined;
  mountSpy.mockReset();
  vi.mocked(usePluginsLoaded).mockReturnValue(true);
});

describe('PluginRenderer', () => {
  it('shows loading state while plugins have not finished loading', () => {
    vi.mocked(usePluginsLoaded).mockReturnValue(false);
    vi.mocked(usePlugins).mockReturnValue([]);

    render(
      <MemoryRouter initialEntries={['/workspaces/ws1/plugin/test-plugin/page1']}>
        <Routes>
          <Route path="/workspaces/:workspace/plugin/:pluginName/*" element={<PluginRenderer />} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('renders the plugin Root with workspaceId and accessToken when loaded', () => {
    vi.mocked(usePlugins).mockReturnValue([makePlugin('test-plugin')]);

    renderPlugin();

    expect(screen.getByTestId('plugin-root')).toBeInTheDocument();
    expect(capturedProps?.host.workspaceId).toBe('my-workspace');
    expect(capturedProps?.host.auth.accessToken).toBe('test-token');
    expect(capturedProps?.host.auth.getAccessToken()).toBe('test-token');
    expect(typeof capturedProps?.host.sdk.platform.useEntitiesListWorkspaces).toBe('function');
  });

  it('does not remount on token renewal and getAccessToken returns the new token', () => {
    vi.mocked(usePlugins).mockReturnValue([makePlugin('test-plugin')]);

    const { rerender } = renderPlugin();
    expect(mountSpy).toHaveBeenCalledTimes(1);

    authState.accessToken = 'renewed-token';
    rerender(
      <MemoryRouter initialEntries={['/workspaces/ws1/plugin/test-plugin/']}>
        <Routes>
          <Route path="/workspaces/:workspace/plugin/:pluginName/*" element={<PluginRenderer />} />
        </Routes>
      </MemoryRouter>
    );

    expect(mountSpy).toHaveBeenCalledTimes(1);
    expect(capturedProps?.host.auth.getAccessToken()).toBe('renewed-token');
  });

  it('shows not found when plugin name does not match any loaded plugin', () => {
    vi.mocked(usePlugins).mockReturnValue([makePlugin('other-plugin')]);

    renderPlugin('missing-plugin');

    expect(screen.getByText(/not found/i)).toBeInTheDocument();
  });

  it('contains a plugin render error in the plugin panel instead of unwinding', () => {
    function ThrowingRoot(): never {
      throw new Error('boom from plugin');
    }
    vi.mocked(usePlugins).mockReturnValue([
      { name: 'test-plugin', Root: ThrowingRoot, navItems: mockNavItems },
    ]);
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

    renderPlugin();

    expect(screen.getByText(/this plugin ran into a problem/i)).toBeInTheDocument();
    expect(screen.getByText(/boom from plugin/)).toBeInTheDocument();
    expect(screen.queryByTestId('plugin-root')).not.toBeInTheDocument();

    consoleError.mockRestore();
  });
});
