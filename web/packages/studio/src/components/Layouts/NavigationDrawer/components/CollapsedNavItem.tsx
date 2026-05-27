// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  Tooltip,
  VerticalNavItem as KuiVerticalNavItem,
  VerticalNavListItem,
} from '@nvidia/foundations-react-core';
import type { NavItem as NavItemData } from '@studio/components/Layouts/NavigationDrawer/types';
import type { FC } from 'react';
import { NavLink } from 'react-router-dom';

interface CollapsedNavItemProps {
  item: NavItemData;
  isActive: (href: string) => boolean;
}

export const CollapsedNavItem: FC<CollapsedNavItemProps> = ({ item, isActive }) => {
  const href = item.href ?? item.subItems?.[0]?.href;
  if (!href || !item.slotIcon) return null;
  const active = item.active ?? isActive(href);

  return (
    <VerticalNavListItem>
      <Tooltip slotContent={item.slotLabel} side="right">
        <KuiVerticalNavItem
          active={active}
          disabled={!href}
          slotStart={item.slotIcon}
          {...item.attributes?.VerticalNavItem}
          className="py-3 px-4"
          asChild
        >
          <NavLink to={href} />
        </KuiVerticalNavItem>
      </Tooltip>
    </VerticalNavListItem>
  );
};
