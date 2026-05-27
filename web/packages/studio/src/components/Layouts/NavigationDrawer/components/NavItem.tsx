// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  VerticalNavCollapsibleContent,
  VerticalNavCollapsibleSection,
  VerticalNavCollapsibleTrigger,
  VerticalNavItem as KuiVerticalNavItem,
  VerticalNavListItem,
  VerticalNavSubList,
  VerticalNavSubListItem,
} from '@nvidia/foundations-react-core';
import type { NavItem as NavItemData } from '@studio/components/Layouts/NavigationDrawer/types';
import { ChevronDown, ChevronUp, ExternalLink } from 'lucide-react';
import { type FC } from 'react';
import { NavLink } from 'react-router-dom';

interface NavItemProps {
  item: NavItemData;
  isActive: (href: string) => boolean;
  accordionOpen: boolean | undefined;
  onAccordionChange: (itemId: string, open: boolean) => void;
}

export const NavItem: FC<NavItemProps> = ({ item, isActive, accordionOpen, onAccordionChange }) => {
  const active = item.active ?? (item.href !== undefined ? isActive(item.href) : false);

  // Section header (no href, no subItems)
  if (item.href === undefined && !item.subItems?.length) {
    return (
      <VerticalNavListItem {...item.attributes?.VerticalNavListItem}>
        <div className="flex items-center gap-2 px-4 py-2" aria-hidden>
          {item.slotIcon}
          <span>{item.slotLabel}</span>
        </div>
      </VerticalNavListItem>
    );
  }

  // Accordion (has subItems)
  if (item.subItems?.length) {
    const isOpen =
      item.open !== undefined ? item.open : (accordionOpen ?? item.defaultOpen !== false);
    return (
      <VerticalNavListItem {...item.attributes?.VerticalNavListItem}>
        <VerticalNavCollapsibleSection
          open={isOpen}
          onOpenChange={(nextOpen) => {
            onAccordionChange(item.id, nextOpen);
            item.onOpenChange?.(nextOpen);
          }}
          {...item.attributes?.VerticalNavCollapsibleSection}
        >
          <VerticalNavCollapsibleTrigger>
            {item.slotIcon}
            <span>{item.slotLabel}</span>
            {isOpen ? <ChevronUp /> : <ChevronDown />}
          </VerticalNavCollapsibleTrigger>
          <VerticalNavCollapsibleContent>
            <VerticalNavSubList {...item.attributes?.VerticalNavSubList}>
              {item.subItems.map((sub) => (
                <VerticalNavSubListItem key={sub.id} {...sub.attributes?.VerticalNavSubListItem}>
                  <KuiVerticalNavItem
                    kind="secondary"
                    active={sub.active ?? (sub.href ? isActive(sub.href) : false)}
                    disabled={!sub.href}
                    slotStart={sub.slotIcon}
                    {...sub.attributes?.VerticalNavItem}
                    asChild
                  >
                    <NavLink to={sub.href ?? ''}>{sub.slotLabel}</NavLink>
                  </KuiVerticalNavItem>
                </VerticalNavSubListItem>
              ))}
            </VerticalNavSubList>
          </VerticalNavCollapsibleContent>
        </VerticalNavCollapsibleSection>
      </VerticalNavListItem>
    );
  }

  // Link (href, no subItems)
  return (
    <VerticalNavListItem {...item.attributes?.VerticalNavListItem}>
      <KuiVerticalNavItem
        active={active}
        disabled={!item.href}
        slotStart={item.slotIcon}
        slotEnd={
          item.attributes?.VerticalNavItem?.target === '_blank' ? <ExternalLink /> : undefined
        }
        className="py-3 px-4"
        {...item.attributes?.VerticalNavItem}
        asChild
      >
        <NavLink to={item.href ?? ''}>{item.slotLabel}</NavLink>
      </KuiVerticalNavItem>
    </VerticalNavListItem>
  );
};
