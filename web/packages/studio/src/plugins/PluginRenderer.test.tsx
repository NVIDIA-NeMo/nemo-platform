import { usePlugins, usePluginsLoaded } from '@studio/plugins/PluginContext';
import { PluginRenderer } from '@studio/plugins/PluginRenderer';
import type { LoadedPlugin } from '@studio/plugins/types';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const authState = vi.hoisted(() => ({ accessToken: 'test-token' }));

const mockCleanup = vi.fn();
const mockMount = vi.fn<LoadedPlugin['mount']>(() => mockCleanup);
const mockNavItems = vi.fn(() => []);

function makePlugin(name: string): LoadedPlugin {
  return { name, mount: mockMount, navItems: mockNavItems };
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
  mockCleanup.mockReset();
  mockMount.mockReset().mockReturnValue(mockCleanup);
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

  it('calls mount with workspaceId and accessToken when plugin is loaded', () => {
    vi.mocked(usePlugins).mockReturnValue([makePlugin('test-plugin')]);

    renderPlugin();

    expect(mockMount).toHaveBeenCalledWith(expect.any(HTMLElement), {
      workspaceId: 'my-workspace',
      auth: { accessToken: 'test-token', getAccessToken: expect.any(Function) },
      basename: '/',
    });
  });

  it('does not remount on token renewal and getAccessToken returns the new token', () => {
    vi.mocked(usePlugins).mockReturnValue([makePlugin('test-plugin')]);

    const { rerender } = renderPlugin();
    expect(mockMount).toHaveBeenCalledTimes(1);

    authState.accessToken = 'renewed-token';
    rerender(
      <MemoryRouter initialEntries={['/workspaces/ws1/plugin/test-plugin/']}>
        <Routes>
          <Route path="/workspaces/:workspace/plugin/:pluginName/*" element={<PluginRenderer />} />
        </Routes>
      </MemoryRouter>
    );

    expect(mockMount).toHaveBeenCalledTimes(1);
    expect(mockCleanup).not.toHaveBeenCalled();
    const props = mockMount.mock.calls[0][1];
    expect(props.auth.getAccessToken()).toBe('renewed-token');
  });

  it('calls cleanup on unmount', () => {
    vi.mocked(usePlugins).mockReturnValue([makePlugin('test-plugin')]);

    const { unmount } = renderPlugin();

    unmount();
    expect(mockCleanup).toHaveBeenCalled();
  });

  it('shows not found when plugin name does not match any loaded plugin', () => {
    vi.mocked(usePlugins).mockReturnValue([makePlugin('other-plugin')]);

    renderPlugin('missing-plugin');

    expect(screen.getByText(/not found/i)).toBeInTheDocument();
  });
});
