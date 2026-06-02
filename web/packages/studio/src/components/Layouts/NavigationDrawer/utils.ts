// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { NavGroup, NavInputItem, NavItem } from '@studio/components/Layouts/NavigationDrawer/types';

export const isGroup = (item: NavInputItem): item is { group?: string; items: NavItem[] } => {
  return Array.isArray((item as { items?: NavItem[] }).items);
};

/** Normalize input into groups. Ungrouped items become their own single-item group. */
export const toGroups = (items: NavInputItem[]): NavGroup[] => {
  const groups: NavGroup[] = [];
  for (const entry of items) {
    if (isGroup(entry)) {
      groups.push({ groupLabel: entry.group, items: entry.items });
    } else {
      groups.push({ items: [entry] });
    }
  }
  return groups;
};
