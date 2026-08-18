// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ActionMenuItem, ActionsMenu } from '@nemo/common/src/components/ActionsMenu';
import { EllipsisVertical } from 'lucide-react';
import { FC } from 'react';

export type QuickActionItem = ActionMenuItem;

interface QuickActionsMenuProps {
  actions: QuickActionItem[];
}

/*
 * QuickActionsMenu is the icon-only preset of ActionsMenu, used for row- and card-level menus.
 */
export const QuickActionsMenuRoot: FC<QuickActionsMenuProps> = ({ actions }) => (
  <ActionsMenu
    actions={actions}
    icon={<EllipsisVertical />}
    ariaLabel="Open quick actions menu"
    data-testid="quick-actions-menu"
  />
);
