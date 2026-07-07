import { usePlugins, usePluginsLoaded } from '@studio/plugins/PluginContext';
import { PluginRenderer } from '@studio/plugins/PluginRenderer';
import type { LoadedPlugin } from '@studio/plugins/types';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const mockCleanup = vi.fn();
const mockMount = vi.fn(() => mockCleanup);
const mockNavItems = vi.fn(() => []);

function makePlugin(name: string): LoadedPlugin {
  return { name, mount: mockMount, navItems: mockNavItems };
}

vi.mock('@studio/plugins/PluginContext', () => ({
  usePlugins: vi.fn(),
  usePluginsLoaded: vi.fn(),
}));
vi.mock('react-oidc-context', () => ({
  useAuth: vi.fn(() => ({ user: { access_token: 'test-token' } })),
}));

vi.mock('@studio/hooks/useWorkspaceFromPath', () => ({
  useWorkspaceFromPath: vi.fn(() => 'my-workspace'),
}));

beforeEach(() => {
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

    render(
      <MemoryRouter initialEntries={['/workspaces/ws1/plugin/test-plugin/']}>
        <Routes>
          <Route path="/workspaces/:workspace/plugin/:pluginName/*" element={<PluginRenderer />} />
        </Routes>
      </MemoryRouter>
    );

    expect(mockMount).toHaveBeenCalledWith(expect.any(HTMLElement), {
      workspaceId: 'my-workspace',
      auth: { accessToken: 'test-token' },
      basename: '/',
    });
  });

  it('calls cleanup on unmount', () => {
    vi.mocked(usePlugins).mockReturnValue([makePlugin('test-plugin')]);

    const { unmount } = render(
      <MemoryRouter initialEntries={['/workspaces/ws1/plugin/test-plugin/']}>
        <Routes>
          <Route path="/workspaces/:workspace/plugin/:pluginName/*" element={<PluginRenderer />} />
        </Routes>
      </MemoryRouter>
    );

    unmount();
    expect(mockCleanup).toHaveBeenCalled();
  });

  it('shows not found when plugin name does not match any loaded plugin', () => {
    vi.mocked(usePlugins).mockReturnValue([makePlugin('other-plugin')]);

    render(
      <MemoryRouter initialEntries={['/workspaces/ws1/plugin/missing-plugin/']}>
        <Routes>
          <Route path="/workspaces/:workspace/plugin/:pluginName/*" element={<PluginRenderer />} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText(/not found/i)).toBeInTheDocument();
  });
});
