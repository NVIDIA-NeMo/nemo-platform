// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { NotFound } from '@studio/components/Layouts/NotFound';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import type { StudioPlugin } from '@studio/plugins/types';
import { isPluginActive } from '@studio/plugins/workspace';
import type { ComponentType, FC } from 'react';

interface PluginScopedRouteProps {
  plugin: StudioPlugin;
  render: ComponentType;
}

/**
 * Gates a plugin-contributed route by workspace scope. Non-active workspaces see a 404 so core
 * routes and navigation stay unchanged outside the plugin's declared workspaces.
 */
export const PluginScopedRoute: FC<PluginScopedRouteProps> = ({ plugin, render: Render }) => {
  const workspace = useWorkspaceFromPath();

  if (!isPluginActive(plugin, workspace)) {
    return (
      <NotFound
        subheader="Page Not Found"
        message="This page is not available in the current workspace."
      />
    );
  }

  return <Render />;
};
