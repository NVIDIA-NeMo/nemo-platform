// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// These types are the plugin contract and must stay in sync with
// web/packages/studio/src/plugins/types.ts in the Studio monorepo.
// They are intentionally duplicated here so the example plugin has no
// build-time dependency on Studio's internal packages.
export interface PluginMountProps {
  workspaceId: string;
  auth: { accessToken: string };
  /** The URL base path where Studio is mounted, e.g. `"/studio/"`. Pass to BrowserRouter as `basename`. */
  basename: string;
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
