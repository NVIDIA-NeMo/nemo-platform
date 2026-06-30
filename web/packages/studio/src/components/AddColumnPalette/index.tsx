// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, Stack, Text, TextInput } from '@nvidia/foundations-react-core';
import {
  COLUMN_TYPE_GROUPS,
  ICON_COLOR_CLASS,
} from '@studio/components/AddColumnPalette/constants';
import type {
  AddColumnSelection,
  ColumnTypeGroup,
  ColumnTypeOption,
} from '@studio/components/AddColumnPalette/types';
import { Search } from 'lucide-react';
import { type FC, useMemo, useState } from 'react';

/** Matches an option against a lowercased search query (name + description). */
const matchesQuery = (option: ColumnTypeOption, query: string): boolean =>
  option.label.toLowerCase().includes(query) || option.description.toLowerCase().includes(query);

interface ColumnTypeCardProps {
  option: ColumnTypeOption;
  onSelect: (selection: AddColumnSelection) => void;
}

/**
 * A single column-type option, rendered as a native `<button>` so it is reachable and
 * activatable by keyboard (Tab to focus, Enter/Space to add) with no drag interaction.
 */
const ColumnTypeCard: FC<ColumnTypeCardProps> = ({ option, onSelect }) => {
  const { icon: Icon, label, description, color, columnType, samplerType } = option;
  return (
    <button
      type="button"
      onClick={() => onSelect({ columnType, samplerType })}
      className="flex cursor-pointer w-full items-center gap-2 rounded-md border border-base bg-surface-raised px-2 py-1.5 text-left transition-colors hover:border-strong hover:bg-surface-hover focus-visible:border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#76b900]"
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

interface ColumnTypeGroupSectionProps {
  group: ColumnTypeGroup;
  options: ColumnTypeOption[];
  onSelect: (selection: AddColumnSelection) => void;
}

/** A labeled group heading (with a count) above its option cards. */
const ColumnTypeGroupSection: FC<ColumnTypeGroupSectionProps> = ({ group, options, onSelect }) => (
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

export interface AddColumnPaletteProps {
  /** Called with the chosen column type when an option is activated. */
  onAddColumn?: (selection: AddColumnSelection) => void;
  className?: string;
}

/**
 * "Add a column" palette for the Data Designer recipe builder.
 *
 * Lists every Data Designer column type as a keyboard-activatable card, grouped by
 * family (Sampler — broken out into its sub-types — then Generate, Transform, Validate,
 * and Data & custom). A search box filters across names and descriptions. Purely
 * presentational: wire {@link AddColumnPaletteProps.onAddColumn} to append a column to
 * the recipe.
 */
export const AddColumnPalette: FC<AddColumnPaletteProps> = ({ onAddColumn, className }) => {
  const [search, setSearch] = useState('');

  const handleSelect = (selection: AddColumnSelection) => onAddColumn?.(selection);

  const filteredGroups = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) {
      return COLUMN_TYPE_GROUPS.map((group) => ({ group, options: group.options }));
    }
    return COLUMN_TYPE_GROUPS.map((group) => ({
      group,
      options: group.options.filter((option) => matchesQuery(option, query)),
    })).filter(({ options }) => options.length > 0);
  }, [search]);

  return (
    <Stack gap="density-lg" className={`flex h-full min-h-0 flex-col ${className ?? ''}`}>
      <Stack gap="density-xxs" className="shrink-0">
        <Text kind="body/bold/md">Add a column</Text>
        <Text kind="body/regular/xs" className="text-secondary">
          Click or press Enter to add
        </Text>
      </Stack>

      <TextInput
        value={search}
        onValueChange={setSearch}
        placeholder="Search column types…"
        slotStart={<Search size={14} className="text-secondary" />}
        className="shrink-0"
        attributes={{ Input: { 'aria-label': 'Search column types' } }}
      />

      <Stack gap="density-lg" className="min-h-0 flex-1 overflow-y-auto">
        {filteredGroups.length === 0 ? (
          <Text kind="body/regular/sm" className="text-secondary">
            No column types match “{search}”.
          </Text>
        ) : (
          filteredGroups.map(({ group, options }) => (
            <ColumnTypeGroupSection
              key={group.id}
              group={group}
              options={options}
              onSelect={handleSelect}
            />
          ))
        )}
      </Stack>
    </Stack>
  );
};
