// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex } from '@nvidia/foundations-react-core';
import { BookOpen, History } from 'lucide-react';

export const PANEL_TAB_ITEMS = [
  {
    value: 'history',
    children: (
      <Flex align="center" gap="density-xs">
        <History size={16} />
        History
      </Flex>
    ),
  },
  {
    value: 'skills',
    children: (
      <Flex align="center" gap="density-xs">
        <BookOpen size={16} />
        Skills
      </Flex>
    ),
  },
];
