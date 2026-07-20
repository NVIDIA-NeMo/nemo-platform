// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  Stack,
  Text,
  VerticalNavList,
  VerticalNavListItem,
  VerticalNavRoot,
} from '@nvidia/foundations-react-core';
import { CollapsedNavItem } from '@studio/components/Layouts/NavigationDrawer/components/CollapsedNavItem';
import { NavItem } from '@studio/components/Layouts/NavigationDrawer/components/NavItem';
import { Props } from '@studio/components/Layouts/NavigationDrawer/types';
import { toGroups } from '@studio/components/Layouts/NavigationDrawer/utils';
import { Fragment, useCallback, useMemo, useState, type FC } from 'react';
import { useLocation } from 'react-router-dom';

export const NavigationDrawer: FC<Props> = ({ items, bottomItems, collapsed = false }) => {
  const { pathname } = useLocation();
  const [accordionState, setAccordionState] = useState<Record<string, boolean>>({});

  const groups = useMemo(() => toGroups(items), [items]);
  const bottomGroups = useMemo(() => (bottomItems ? toGroups(bottomItems) : []), [bottomItems]);

  // Active item = the nav href that's the longest prefix of the current
  const matchedHref = useMemo(() => {
    const hrefs = [...groups, ...bottomGroups]
      .flatMap((g) => g.items)
      .flatMap((i) => [i.href, ...(i.subItems ?? []).map((s) => s.href)])
      .filter((h): h is string => typeof h === 'string');
    const matching = hrefs.filter((h) => pathname === h || pathname.startsWith(`${h}/`));
    return matching.reduce<string | null>(
      (best, h) => (best === null || h.length > best.length ? h : best),
      null
    );
  }, [groups, bottomGroups, pathname]);

  const isActive = useCallback((href: string) => href === matchedHref, [matchedHref]);

  const handleAccordionChange = (itemId: string, open: boolean) => {
    setAccordionState((prev) => ({ ...prev, [itemId]: open }));
  };

  const renderGroups = (groupList: ReturnType<typeof toGroups>) =>
    groupList.map((group, groupIndex) => (
      <Fragment key={groupIndex}>
        {!collapsed && group.groupLabel && (
          <VerticalNavListItem className={groupIndex > 0 ? 'pt-4 px-4' : 'px-4'}>
            <Text kind="body/semibold/sm" className="text-subtle">
              {group.groupLabel}
            </Text>
          </VerticalNavListItem>
        )}
        {group.items.map((item) =>
          collapsed ? (
            <CollapsedNavItem key={item.id} item={item} isActive={isActive} />
          ) : (
            <NavItem
              key={item.id}
              item={item}
              isActive={isActive}
              accordionOpen={accordionState[item.id]}
              onAccordionChange={handleAccordionChange}
            />
          )
        )}
      </Fragment>
    ));

  const hasBottomItems = bottomGroups.length > 0;

  if (!hasBottomItems) {
    return (
      <VerticalNavRoot
        className={`overflow-hidden transition-[width] duration-200 ${collapsed ? 'w-12' : 'w-60'}`}
      >
        <VerticalNavList className="pt-2 w-max min-w-full">{renderGroups(groups)}</VerticalNavList>
      </VerticalNavRoot>
    );
  }

  return (
    <Stack
      className={`h-[calc(100vh-var(--nv-app-bar-height))] transition-[width] duration-200 overflow-hidden ${collapsed ? 'w-12' : 'w-60'}`}
    >
      <VerticalNavRoot className="flex-1 min-h-0 w-full overflow-y-auto overflow-x-hidden">
        <VerticalNavList className="pt-2 w-max min-w-full">{renderGroups(groups)}</VerticalNavList>
      </VerticalNavRoot>
      <VerticalNavRoot className="shrink-0 h-auto! w-full">
        <VerticalNavList className="h-auto! w-max min-w-full pb-2">
          {renderGroups(bottomGroups)}
        </VerticalNavList>
      </VerticalNavRoot>
    </Stack>
  );
};
