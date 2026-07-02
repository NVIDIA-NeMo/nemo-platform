// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { ICON_COLOR_CLASS } from '@studio/components/AddColumnPalette/constants';
import type {
  AddColumnSelection,
  ColumnTypeOption,
} from '@studio/components/AddColumnPalette/types';
import type { FC } from 'react';

interface ColumnTypeCardProps {
  option: ColumnTypeOption;
  onSelect: (selection: AddColumnSelection) => void;
}

/**
 * A single column-type option, rendered as a native `<button>` so it is reachable and
 * activatable by keyboard (Tab to focus, Enter/Space to add) with no drag interaction.
 */
export const ColumnTypeCard: FC<ColumnTypeCardProps> = ({ option, onSelect }) => {
  const { icon: Icon, label, description, color, columnType, samplerType } = option;
  return (
    <button
      type="button"
      onClick={() => onSelect({ columnType, samplerType })}
      className="flex cursor-pointer w-full items-center gap-2 rounded-md border border-base bg-surface-raised px-2 py-1.5 text-left transition-colors hover:border-interaction-primary-base hover:bg-surface-hover focus-visible:border-interaction-primary-base focus-visible:outline-none active:border-interaction-primary-selected"
    >
      <Flex
        align="center"
        justify="center"
        className="size-[26px] shrink-0 rounded-sm bg-surface-sunken"
      >
        <Icon size={15} className={ICON_COLOR_CLASS[color]} aria-hidden />
      </Flex>
      <Stack gap="density-xxs" className="min-w-0">
        <Text kind="body/semibold/sm" className="truncate text-primary">
          {label}
        </Text>
        <Text kind="body/regular/xs" className="truncate text-secondary">
          {description}
        </Text>
      </Stack>
    </button>
  );
};
