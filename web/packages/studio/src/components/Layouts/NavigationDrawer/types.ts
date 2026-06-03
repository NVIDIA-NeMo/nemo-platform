// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type {
  VerticalNavCollapsibleSection,
  VerticalNavItem,
  VerticalNavListItem,
  VerticalNavSubList,
  VerticalNavSubListItem,
} from '@nvidia/foundations-react-core';
import type { ComponentPropsWithoutRef, ReactNode } from 'react';

export interface NavSubItem {
  id: string;
  slotLabel?: ReactNode;
  slotIcon?: ReactNode;
  href?: string;
  active?: boolean;
  disabled?: boolean;
  attributes?: {
    VerticalNavItem?: Omit<ComponentPropsWithoutRef<typeof VerticalNavItem>, 'children'>;
    VerticalNavSubListItem?: ComponentPropsWithoutRef<typeof VerticalNavSubListItem>;
  };
}

export interface NavItem {
  id: string;
  slotLabel?: ReactNode;
  slotIcon?: ReactNode;
  href?: string;
  active?: boolean;
  disabled?: boolean;
  defaultOpen?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  subItems?: NavSubItem[];
  attributes?: {
    VerticalNavItem?: Omit<ComponentPropsWithoutRef<typeof VerticalNavItem>, 'children'>;
    VerticalNavListItem?: ComponentPropsWithoutRef<typeof VerticalNavListItem>;
    VerticalNavCollapsibleSection?: ComponentPropsWithoutRef<typeof VerticalNavCollapsibleSection>;
    VerticalNavSubList?: ComponentPropsWithoutRef<typeof VerticalNavSubList>;
  };
}

export type NavInputItem = NavItem | { group?: string; items: NavItem[] };

export interface Props {
  items: NavInputItem[];
  bottomItems?: NavInputItem[];
  collapsed?: boolean;
}

export interface NavGroup {
  groupLabel?: string;
  items: NavItem[];
}
