// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { NavGroup, NavInputItem, NavItem } from '@studio/components/Layouts/NavigationDrawer/types';

export const isGroup = (item: NavInputItem): item is { group?: string; items: NavItem[] } => {
  return Array.isArray((item as { items?: NavItem[] }).items);
};

/**
 * An item's own `active` wins when set. An item with no href is never active — a parent highlights
 * because its own landing page matched, not because one of its children did.
 */
export const resolveActive = (
  item: { active?: boolean; href?: string },
  isActive: (href: string) => boolean
): boolean => item.active ?? (item.href !== undefined ? isActive(item.href) : false);

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

/**
 * Flatten parents and children into one list for the collapsed rail, which has no room for
 * accordions. A parent that is only a container (no href) drops out; its children follow it.
 */
export const flattenForRail = (items: NavItem[]): NavItem[] =>
  items.flatMap((item) => [
    ...(item.href !== undefined ? [{ ...item, subItems: undefined }] : []),
    ...(item.subItems ?? []),
  ]);
