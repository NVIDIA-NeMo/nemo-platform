// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { ColumnTypeCard } from '@studio/components/AddColumnPalette/ColumnTypeCard';
import type {
  AddColumnSelection,
  ColumnTypeGroup,
  ColumnTypeOption,
} from '@studio/components/AddColumnPalette/types';
import type { FC } from 'react';

interface ColumnTypeGroupSectionProps {
  group: ColumnTypeGroup;
  options: ColumnTypeOption[];
  onSelect: (selection: AddColumnSelection) => void;
}

/** A labeled group heading (with a count) above its option cards. */
export const ColumnTypeGroupSection: FC<ColumnTypeGroupSectionProps> = ({
  group,
  options,
  onSelect,
}) => (
  <Stack gap="1" className="w-full">
    <Flex align="center" gap="density-xs">
      <Text kind="label/bold/xs" className="uppercase tracking-wide text-secondary">
        {group.label}
      </Text>
    </Flex>
    <Stack gap="1.5" className="w-full">
      {options.map((option) => (
        <ColumnTypeCard key={option.id} option={option} onSelect={onSelect} />
      ))}
    </Stack>
  </Stack>
);
