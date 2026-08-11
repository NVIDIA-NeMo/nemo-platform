// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ExpandableNavItem } from '@studio/components/Layouts/NavigationDrawer/components/NavItem/ExpandableNavItem';
import { NavLinkItem } from '@studio/components/Layouts/NavigationDrawer/components/NavItem/NavLinkItem';
import type { NavItem as NavItemData } from '@studio/components/Layouts/NavigationDrawer/types';
import type { FC } from 'react';

interface NavItemProps {
  item: NavItemData;
  isActive: (href: string) => boolean;
  accordionOpen: boolean | undefined;
  onAccordionChange: (itemId: string, open: boolean) => void;
}

export const NavItem: FC<NavItemProps> = ({ item, isActive, accordionOpen, onAccordionChange }) =>
  item.subItems?.length ? (
    <ExpandableNavItem
      item={item}
      isActive={isActive}
      accordionOpen={accordionOpen}
      onAccordionChange={onAccordionChange}
    />
  ) : (
    <NavLinkItem item={item} isActive={isActive} />
  );
