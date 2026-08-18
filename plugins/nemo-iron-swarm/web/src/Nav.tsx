// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getIronSwarmRunListRoute } from '@iron-swarm/paths';
import type { PluginNavGroup } from '@iron-swarm/types';

/**
 * Iron Swarm's entry in Studio's side nav. Studio renders these under the
 * named group, so installing the plugin is what puts the item there — Studio
 * carries no iron-swarm-specific nav code.
 */
export const navItems = (workspaceId: string): PluginNavGroup[] => [
  {
    group: 'Governance',
    items: [
      {
        id: 'iron-swarm',
        iconName: 'swords',
        label: 'Iron Swarm',
        href: getIronSwarmRunListRoute(workspaceId),
      },
    ],
  },
];
