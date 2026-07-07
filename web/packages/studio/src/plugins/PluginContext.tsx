import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { isTrustedBundleUrl } from '@studio/plugins/security';
import type { LoadedPlugin, PluginManifest } from '@studio/plugins/types';
import { logger } from '@studio/util/logger';
import { createContext, type ReactNode, useContext, useEffect, useState } from 'react';

interface PluginContextValue {
  plugins: LoadedPlugin[];
  /** All plugin names returned by /apis/plugins, including headless ones. */
  installedNames: ReadonlySet<string>;
  isLoaded: boolean;
}

const PluginContext = createContext<PluginContextValue>({
  plugins: [],
  installedNames: new Set(),
  isLoaded: false,
});

// eslint-disable-next-line react-refresh/only-export-components
export const usePlugins = (): LoadedPlugin[] => useContext(PluginContext).plugins;
// eslint-disable-next-line react-refresh/only-export-components
export const usePluginsLoaded = (): boolean => useContext(PluginContext).isLoaded;
/** Returns true if the named plugin is registered in /apis/plugins (with or without a bundle). */
// eslint-disable-next-line react-refresh/only-export-components
export const usePluginInstalled = (name: string): boolean =>
  useContext(PluginContext).installedNames.has(name);

function isValidPluginManifest(obj: unknown): obj is PluginManifest {
  if (typeof obj !== 'object' || obj === null) return false;
  const o = obj as Record<string, unknown>;
  return typeof o.name === 'string' && (typeof o.bundleUrl === 'string' || o.bundleUrl === null);
}

async function loadPlugin(manifest: PluginManifest, baseUrl: string): Promise<LoadedPlugin | null> {
  if (manifest.bundleUrl === null) {
    // Plugin registered without a web bundle — no UI to mount or nav to show.
    return null;
  }
  if (!isTrustedBundleUrl(manifest.bundleUrl)) {
    logger.warn(`[plugins] Rejected untrusted bundle URL: ${manifest.bundleUrl}`);
    return null;
  }
  // Prefix with the API base URL so the import resolves against the backend
  // host, not the Studio dev server (which may run on a different origin).
  const absoluteUrl = `${baseUrl}${manifest.bundleUrl}`;
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const module = (await import(/* @vite-ignore */ absoluteUrl)) as any;
    if (typeof module.mount !== 'function' || typeof module.navItems !== 'function') {
      logger.warn(`[plugins] Plugin "${manifest.name}" missing required exports (mount, navItems)`);
      return null;
    }
    return { name: manifest.name, mount: module.mount, navItems: module.navItems };
  } catch (err) {
    logger.warn(`[plugins] Failed to load plugin "${manifest.name}":`, err);
    return null;
  }
}

interface PluginProviderProps {
  children: ReactNode;
}

export const PluginProvider = ({ children }: PluginProviderProps) => {
  const [plugins, setPlugins] = useState<LoadedPlugin[]>([]);
  const [installedNames, setInstalledNames] = useState<ReadonlySet<string>>(new Set());
  const [isLoaded, setIsLoaded] = useState(false);

  useEffect(() => {
    // Falls back to same-origin when PLATFORM_BASE_URL is not configured
    const baseUrl = PLATFORM_BASE_URL ?? '';
    fetch(`${baseUrl}/apis/plugins`)
      .then((res) => {
        if (!res.ok) throw new Error(`/apis/plugins returned ${res.status}`);
        return res.json() as Promise<unknown>;
      })
      .then(async (data) => {
        if (!Array.isArray(data)) {
          logger.warn('[plugins] /apis/plugins did not return an array');
          return;
        }
        const invalid = (data as unknown[]).filter((item) => !isValidPluginManifest(item));
        if (invalid.length > 0) {
          logger.warn(
            `[plugins] /apis/plugins returned ${invalid.length} invalid manifest(s) — skipping`
          );
        }
        const manifests = (data as unknown[]).filter(isValidPluginManifest);
        const loaded = await Promise.all(manifests.map((m) => loadPlugin(m, baseUrl)));
        // Set both in the same render cycle so consumers never observe
        // installedNames populated while plugins is still empty.
        setInstalledNames(new Set(manifests.map((m) => m.name)));
        setPlugins(loaded.filter((p): p is LoadedPlugin => p !== null));
      })
      .catch((err) => {
        logger.warn('[plugins] Failed to fetch plugin manifest:', err);
      })
      .finally(() => {
        setIsLoaded(true);
      });
  }, []);

  return (
    <PluginContext.Provider value={{ plugins, installedNames, isLoaded }}>
      {children}
    </PluginContext.Provider>
  );
};
