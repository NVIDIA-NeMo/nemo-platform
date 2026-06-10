// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useAgentsListAgents } from '@nemo/sdk/generated/agents/api';
import {
  Block,
  Button,
  DropdownContent,
  DropdownHeading,
  DropdownItem,
  DropdownRoot,
  DropdownSection,
  DropdownTrigger,
  Flex,
  Stack,
  Text,
  TextInput,
} from '@nvidia/foundations-react-core';
import { Box, Check, ChevronDown, HatGlasses, Search } from 'lucide-react';
import { useMemo, useState, type ChangeEvent, type FC } from 'react';

interface AgentPickerProps {
  workspace: string;
  /** Currently selected agent name from `?agent=`, or null for the Models scope. */
  value: string | null;
  /** Pass null to select the Models scope (plain chat / no agent context). */
  onChange: (next: string | null) => void;
  disabled?: boolean;
}

/**
 * Test-scope picker. Selecting "Compare Models Only" clears the agent context (plain
 * chat / models-only) by calling `onChange(null)`; selecting an agent calls
 * `onChange(name)` which the route maps to `?agent=`. Built from the same
 * composed Kaizen dropdown primitives as `ModelDropdown`/`DatasetDropdown`:
 * a bordered trigger plus a searchable, sectioned menu.
 */
export const AgentPicker: FC<AgentPickerProps> = ({ workspace, value, onChange, disabled }) => {
  const { data, isLoading } = useAgentsListAgents(workspace, undefined, {
    query: { enabled: !!workspace },
  });
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');

  const agentNames = useMemo(
    () => (data?.data ?? []).map((a) => a.name).filter((n): n is string => !!n),
    [data]
  );

  const filteredAgents = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return agentNames;
    return agentNames.filter((name) => name.toLowerCase().includes(q));
  }, [agentNames, search]);

  const triggerLabel = isLoading ? 'Loading agents…' : (value ?? 'Compare Models Only');

  const handleOpenChange = (next: boolean) => {
    setOpen(next);
    if (!next) setSearch('');
  };

  const select = (next: string | null) => {
    onChange(next);
    setOpen(false);
  };

  return (
    <DropdownRoot open={open} onOpenChange={handleOpenChange}>
      <DropdownTrigger asChild showChevron={false}>
        <Button
          kind="secondary"
          disabled={disabled || isLoading}
          aria-label="Select test scope"
          data-testid="agent-picker-trigger"
          className="w-[280px] overflow-hidden !border-[var(--border-color-interaction-base)] !bg-[var(--background-color-interaction-base)] hover:!border-[var(--border-color-interaction-hover)] [&[data-state=open]]:!border-[var(--border-color-interaction-selected)]"
        >
          <Flex align="center" gap="density-sm" className="min-w-0 w-full justify-between">
            <Flex align="center" gap="density-sm" className="min-w-0 flex-1">
              {!isLoading &&
                (value === null ? (
                  <Box size={16} className="text-base flex-shrink-0" />
                ) : (
                  <HatGlasses size={16} className="text-base flex-shrink-0" />
                ))}
              <Text kind="label/regular/md" className="truncate">
                {triggerLabel}
              </Text>
            </Flex>
            <ChevronDown
              size={16}
              className={`flex-shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
            />
          </Flex>
        </Button>
      </DropdownTrigger>
      <DropdownContent
        align="start"
        side="bottom"
        data-testid="agent-picker-content"
        className="min-w-[320px]"
        style={{ width: 320 }} // eslint-disable-line no-restricted-syntax -- KUI DropdownContent needs explicit width
      >
        <Block className="p-2 w-full sticky top-0 bg-surface z-10">
          <TextInput
            name="agent-filter"
            className="overflow-hidden"
            slotStart={<Search />}
            placeholder="Search by agents..."
            value={search}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setSearch(e.target.value)}
            // Keep typing from being captured by the menu's keyboard navigation.
            onKeyDownCapture={(e) => e.stopPropagation()}
            onKeyUpCapture={(e) => e.stopPropagation()}
          />
        </Block>
        <Stack className="overflow-auto max-h-[300px] w-full">
          <DropdownSection>
            <DropdownItem data-testid="agent-picker-models-option" onSelect={() => select(null)}>
              <Flex align="center" justify="between" gap="density-sm" className="min-w-0 w-full">
                <Flex align="center" gap="density-sm" className="min-w-0">
                  <Box size={16} className="text-base flex-shrink-0" />
                  <Text className="truncate">Compare Models Only</Text>
                </Flex>
                {value === null && <Check size={16} className="flex-shrink-0" />}
              </Flex>
            </DropdownItem>
          </DropdownSection>
          <DropdownSection>
            <DropdownHeading>Compare Agents</DropdownHeading>
            {filteredAgents.length > 0 ? (
              filteredAgents.map((name) => (
                <DropdownItem
                  key={name}
                  data-testid="agent-picker-agent-option"
                  onSelect={() => select(name)}
                >
                  <Flex
                    align="center"
                    justify="between"
                    gap="density-sm"
                    className="min-w-0 w-full"
                  >
                    <Flex align="center" gap="density-sm" className="min-w-0">
                      <HatGlasses size={16} className="text-base flex-shrink-0" />
                      <Text className="truncate">{name}</Text>
                    </Flex>
                    {value === name && <Check size={16} className="flex-shrink-0" />}
                  </Flex>
                </DropdownItem>
              ))
            ) : (
              <DropdownItem disabled>
                <Text className="text-secondary">
                  {isLoading ? 'Loading agents…' : 'No agents found'}
                </Text>
              </DropdownItem>
            )}
          </DropdownSection>
        </Stack>
      </DropdownContent>
    </DropdownRoot>
  );
};
