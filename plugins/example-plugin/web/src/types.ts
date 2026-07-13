// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// These types are the plugin contract and must stay in sync with
// web/packages/studio/src/plugins/types.ts in the Studio monorepo.
// They are intentionally duplicated here so the example plugin has no
// build-time dependency on Studio's internal packages.

// Minimal mirror of Studio's PluginSdk — only the hooks this example calls, so it
// stays free of the private @nemo/sdk package.
export interface PluginSdk {
  platform: {
    useEntitiesListWorkspaces: (
      params?: { page?: number; page_size?: number },
      options?: { query?: { enabled?: boolean; staleTime?: number } }
    ) => {
      data?: { data?: Array<{ name: string }> };
      isPending: boolean;
      isError: boolean;
    };
  };
}

export interface PluginHost {
  workspaceId: string;
  auth: {
    accessToken: string;
    getAccessToken: () => string;
  };
  sdk: PluginSdk;
}

export interface PluginRootProps {
  host: PluginHost;
}

export interface PluginNavItem {
  id: string;
  iconName: string;
  label: string;
  href: string;
}

export interface PluginNavGroup {
  group: string;
  items: PluginNavItem[];
}
