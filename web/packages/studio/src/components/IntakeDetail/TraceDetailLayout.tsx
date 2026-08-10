// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, Stack } from '@nvidia/foundations-react-core';
import type { FC, ReactNode } from 'react';

interface TraceDetailLayoutProps {
  navigation: ReactNode;
  children: ReactNode;
}

/** Shared two-pane shell for Session, trace, and span detail selections. */
export const TraceDetailLayout: FC<TraceDetailLayoutProps> = ({ navigation, children }) => (
  <Flex align="start" gap="density-md" className="min-w-0">
    <aside
      data-testid="trace-trajectory-sidebar"
      className="sticky top-density-lg hidden max-h-[calc(100vh-6rem)] w-[18rem] shrink-0 self-start overflow-y-auto rounded-lg bg-surface-raised p-density-xs lg:block"
    >
      {navigation}
    </aside>
    <Stack gap="density-lg" className="min-w-0 flex-1">
      {children}
    </Stack>
  </Flex>
);
