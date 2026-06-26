// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SidePanel } from '@nvidia/foundations-react-core';
import type { FC, ReactNode } from 'react';

export interface FilesetSidePanelWrapperProps {
  open: boolean;
  onOpenChange: (isOpen: boolean) => void;
  slotHeading?: ReactNode;
  children: ReactNode;
}

export const FilesetSidePanelWrapper: FC<FilesetSidePanelWrapperProps> = ({
  open,
  onOpenChange,
  slotHeading,
  children,
}) => (
  <SidePanel
    slotHeading={slotHeading}
    side="right"
    open={open}
    onOpenChange={onOpenChange}
    attributes={{
      SidePanelHeading: { className: 'font-normal' },
      SidePanelMain: { className: 'p-0 overflow-x-hidden' },
      SidePanelCloseButton: { type: 'button' },
    }}
    bordered
    modal
    className="w-[960px]"
  >
    {children}
  </SidePanel>
);
