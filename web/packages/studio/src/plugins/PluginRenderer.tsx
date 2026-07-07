import { BASE_URL } from '@studio/constants/environment';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { usePlugins, usePluginsLoaded } from '@studio/plugins/PluginContext';
import { useEffect, useRef, type ReactElement } from 'react';
import { useAuth } from 'react-oidc-context';
import { useParams } from 'react-router-dom';

export const PluginRenderer = (): ReactElement => {
  const { pluginName } = useParams<{ pluginName: string }>();
  const plugins = usePlugins();
  const isLoaded = usePluginsLoaded();
  const workspace = useWorkspaceFromPath();
  const { user } = useAuth();
  const containerRef = useRef<HTMLDivElement>(null);

  const plugin = plugins.find((p) => p.name === pluginName);
  const accessToken = user?.access_token ?? '';
  const accessTokenRef = useRef(accessToken);
  accessTokenRef.current = accessToken;

  useEffect(() => {
    if (!plugin || !containerRef.current) return;

    return plugin.mount(containerRef.current, {
      workspaceId: workspace,
      auth: {
        accessToken: accessTokenRef.current,
        getAccessToken: () => accessTokenRef.current,
      },
      basename: BASE_URL ?? '/',
    });
  }, [plugin, workspace]);

  if (!isLoaded) {
    return (
      <div className="flex h-full items-center justify-center text-subtle">Loading plugin…</div>
    );
  }

  if (!plugin) {
    return (
      <div className="flex h-full items-center justify-center text-subtle">
        Plugin &ldquo;{pluginName}&rdquo; not found.
      </div>
    );
  }

  return <div ref={containerRef} className="size-full" />;
};
