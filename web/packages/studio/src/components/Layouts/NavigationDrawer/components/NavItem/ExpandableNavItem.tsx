// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { VerticalNavListItem, VerticalNavSubList } from '@nvidia/foundations-react-core';
import { NavSubItem } from '@studio/components/Layouts/NavigationDrawer/components/NavItem/NavSubItem';
import { StudioNavItem } from '@studio/components/Layouts/NavigationDrawer/components/StudioNavItem';
import { SUB_LIST_CLASS } from '@studio/components/Layouts/NavigationDrawer/styles';
import type { NavItem as NavItemData } from '@studio/components/Layouts/NavigationDrawer/types';
import { resolveActive } from '@studio/components/Layouts/NavigationDrawer/utils';
import { ChevronDown, ChevronLeft } from 'lucide-react';
import type { FC } from 'react';
import { NavLink } from 'react-router';

interface ExpandableNavItemProps {
  item: NavItemData;
  isActive: (href: string) => boolean;
  accordionOpen: boolean | undefined;
  onAccordionChange: (itemId: string, open: boolean) => void;
}

/**
 * A parent row and its sub-list. KUI's collapsible is a native <details>/<summary>, whose summary
 * cannot be a link, so the row is composed here: a link plus a sibling disclosure button.
 */
export const ExpandableNavItem: FC<ExpandableNavItemProps> = ({
  item,
  isActive,
  accordionOpen,
  onAccordionChange,
}) => {
  const { href, subItems = [] } = item;
  const isOpen = accordionOpen ?? item.defaultOpen !== false;
  const subListId = `${item.id}-submenu`;
  const chevron = isOpen ? <ChevronDown /> : <ChevronLeft />;
  const disclosure = { 'aria-expanded': isOpen, 'aria-controls': subListId };
  const labelText = typeof item.slotLabel === 'string' ? item.slotLabel : undefined;
  const toggle = () => onAccordionChange(item.id, !isOpen);

  return (
    <VerticalNavListItem {...item.attributes?.VerticalNavListItem}>
      {/* The chevron overlays the row so the row's highlight still spans its full width. */}
      <div className="relative flex items-center">
        <StudioNavItem
          active={resolveActive(item, isActive)}
          slotStart={item.slotIcon}
          slotEnd={href === undefined ? chevron : undefined}
          padding={href === undefined ? 'fullWidth' : 'trailingToggle'}
          {...item.attributes?.VerticalNavItem}
        >
          {href === undefined ? (
            <button type="button" onClick={toggle} {...disclosure}>
              {item.slotLabel}
            </button>
          ) : (
            <NavLink to={href}>{item.slotLabel}</NavLink>
          )}
        </StudioNavItem>
        {href !== undefined && (
          <button
            type="button"
            onClick={toggle}
            className="absolute right-0 h-full cursor-pointer px-3 text-subtle"
            aria-label={
              labelText ? `${isOpen ? 'Collapse' : 'Expand'} ${labelText}` : 'Toggle submenu'
            }
            {...disclosure}
          >
            {chevron}
          </button>
        )}
      </div>
      {isOpen && (
        <VerticalNavSubList
          id={subListId}
          className={SUB_LIST_CLASS}
          {...item.attributes?.VerticalNavSubList}
        >
          {subItems.map((sub) => (
            <NavSubItem key={sub.id} item={sub} isActive={isActive} />
          ))}
        </VerticalNavSubList>
      )}
    </VerticalNavListItem>
  );
};
