// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  DropdownRoot,
  DropdownTrigger,
  DropdownContent,
  DropdownItem,
  Flex,
} from '@nvidia/foundations-react-core';
import { FC } from 'react';

export interface QuickActionItem {
  slotLabel: string;
  slotIcon?: React.ReactNode;
  onSelect: () => void;
}

interface ActionMenuProps {
  slotTrigger: React.ReactNode;
  actions: QuickActionItem[];
}

/**
 * Dropdown menu for evaluation configuration actions.
 * Supports actions like "View Details" and "Create Evaluation".
 */
export const ActionMenu: FC<ActionMenuProps> = ({ actions, slotTrigger }) => {
  const handleItemClicked =
    (action: QuickActionItem): React.MouseEventHandler<HTMLButtonElement> =>
    (e) => {
      e.stopPropagation();
      action.onSelect();
    };

  return (
    <DropdownRoot>
      <DropdownTrigger asChild showChevron={false} onClick={(e) => e.stopPropagation()}>
        {slotTrigger}
      </DropdownTrigger>
      <DropdownContent align="end">
        {actions.map((action, key) => (
          <DropdownItem key={`action-${key}`} onClick={handleItemClicked(action)}>
            <Flex gap="density-xs" align="center">
              {action.slotIcon}
              {action.slotLabel}
            </Flex>
          </DropdownItem>
        ))}
      </DropdownContent>
    </DropdownRoot>
  );
};
