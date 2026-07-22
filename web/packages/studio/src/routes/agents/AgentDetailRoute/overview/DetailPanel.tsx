// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, Stack, Text } from '@nvidia/foundations-react-core';
import type { FC, ReactNode } from 'react';

interface DetailPanelProps {
  title: string;
  /** Rendered on the right of the header (e.g. a count or a "View all" link). */
  slotAction?: ReactNode;
  /** When true, the body has no padding so rows can own their own dividers. */
  flush?: boolean;
  children: ReactNode;
}

/** Bordered raised-surface card with a titled header, matching the overview panels. */
export const DetailPanel: FC<DetailPanelProps> = ({ title, slotAction, flush, children }) => (
  <Stack className="w-full rounded-xl border border-base bg-surface-raised">
    <Flex align="center" justify="between" className="px-4 py-3.5">
      <Text kind="body/bold/sm">{title}</Text>
      {slotAction}
    </Flex>
    <div className="h-px w-full bg-base" />
    <div className={flush ? '' : 'p-4'}>{children}</div>
  </Stack>
);
