// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  Button,
  Divider,
  DropdownContent,
  DropdownDividerItemEntry,
  DropdownItem,
  DropdownRoot,
  DropdownTrigger,
  Flex,
} from '@nvidia/foundations-react-core';
import { EllipsisVertical } from 'lucide-react';
import React, { FC } from 'react';

export interface QuickActionItem {
  label: string;
  onSelect: () => void;
  icon?: React.ReactElement<{ size?: number; fill?: string; className?: string }>;
  disabled?: boolean;
  danger?: boolean;
  divider?: Omit<DropdownDividerItemEntry, 'kind'>;
}

interface QuickActionsMenuProps {
  actions: QuickActionItem[];
}

/*
 * QuickActionsMenu is a wrapper around Kaizen's Menu component that standardizes
 * the alignment of menus and other sizes/behaviours.
 */
export const QuickActionsMenuRoot: FC<QuickActionsMenuProps> = ({ actions }) => {
  return (
    <DropdownRoot>
      <DropdownTrigger
        asChild
        data-testid="quick-actions-menu-trigger"
        onClick={(e) => e.stopPropagation()}
        showChevron={false}
      >
        <Button kind="tertiary" aria-label="Open quick actions menu">
          <EllipsisVertical />
        </Button>
      </DropdownTrigger>
      <DropdownContent
        align="end"
        side="bottom"
        data-testid="quick-actions-menu-content"
        className="w-[180px] min-w-[180px]"
      >
        {actions.map((action, key) => (
          <React.Fragment key={`action-${key}`}>
            <DropdownItem
              data-testid="quick-actions-menu-item"
              disabled={action.disabled}
              onClick={(e) => {
                e.stopPropagation();
                action.onSelect();
              }}
              danger={action.danger}
            >
              <Flex align="center" gap="density-sm" className="pr-6">
                {action.icon && React.cloneElement(action.icon, { size: 20, fill: 'solid' })}
                {action.label}
              </Flex>
            </DropdownItem>
            {action.divider && <Divider width={action.divider.width} />}
          </React.Fragment>
        ))}
      </DropdownContent>
    </DropdownRoot>
  );
};
