// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { VerticalNavListItem } from '@nvidia/foundations-react-core';
import { StudioNavItem } from '@studio/components/Layouts/NavigationDrawer/components/StudioNavItem';
import type { NavItem as NavItemData } from '@studio/components/Layouts/NavigationDrawer/types';
import { resolveActive } from '@studio/components/Layouts/NavigationDrawer/utils';
import type { FC } from 'react';
import { NavLink } from 'react-router';

interface NavLinkItemProps {
  item: NavItemData;
  isActive: (href: string) => boolean;
}

/** A leaf row: one link, no children. */
export const NavLinkItem: FC<NavLinkItemProps> = ({ item, isActive }) => {
  const { href } = item;
  if (href === undefined) return null;

  return (
    <VerticalNavListItem {...item.attributes?.VerticalNavListItem}>
      <StudioNavItem
        active={resolveActive(item, isActive)}
        slotStart={item.slotIcon}
        {...item.attributes?.VerticalNavItem}
      >
        <NavLink to={href}>{item.slotLabel}</NavLink>
      </StudioNavItem>
    </VerticalNavListItem>
  );
};
