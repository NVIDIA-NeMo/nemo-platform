// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Studio hands the plugin a single `host` handle at the root. Threading it
// through every component would touch every call site, so `Root` puts it on a
// context and these hooks mirror the Studio APIs the moved code already used
// (`useWorkspaceFromPath`, `useToast`, `useBreadcrumbs`).

import type { PluginHost } from '@iron-swarm/types';
import { createContext, useContext, useEffect, useMemo, type ReactNode } from 'react';


const HostContext = createContext<PluginHost | null>(null);

export const HostProvider = ({ host, children }: { host: PluginHost; children: ReactNode }) => (
  <HostContext.Provider value={host}>{children}</HostContext.Provider>
);

export const useHost = (): PluginHost => {
  const host = useContext(HostContext);
  if (!host) {
    throw new Error('useHost must be used within the iron-swarm plugin Root');
  }
  return host;
};

export const useWorkspace = (): string => useHost().workspaceId;

/** Subset of Studio's toast object that this plugin uses, routed to Studio's toaster. */
export interface PluginToast {
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
  warning: (message: string) => void;
}

export const useToast = (): PluginToast => {
  const { notifications } = useHost();
  return useMemo(
    () => ({
      success: (message: string) => notifications.notify(message, 'success'),
      error: (message: string) => notifications.notify(message, 'error'),
      info: (message: string) => notifications.notify(message, 'info'),
      warning: (message: string) => notifications.notify(message, 'warning'),
    }),
    [notifications]
  );
};

export interface BreadcrumbsItemProps {
  href?: string;
  slotLabel: ReactNode;
}

/**
 * Studio's breadcrumb bar lives outside the plugin's subtree, so it is written
 * through the host. Studio clears the trail when the plugin unmounts but not
 * between pages inside it, hence the cleanup.
 */
export const useBreadcrumbs = ({ items }: { items?: BreadcrumbsItemProps[] } = {}): void => {
  const { breadcrumbs } = useHost();
  // Serialized so a fresh array literal on each render doesn't re-fire the effect.
  const trail = useMemo(
    () =>
      (items ?? [])
        .filter((item) => typeof item.slotLabel === 'string')
        .map((item) => ({ label: item.slotLabel as string, href: item.href })),
    [items]
  );
  const key = JSON.stringify(trail);

  useEffect(() => {
    if (trail.length === 0) return;
    breadcrumbs.set(trail);
    return () => breadcrumbs.set([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, breadcrumbs]);
};
