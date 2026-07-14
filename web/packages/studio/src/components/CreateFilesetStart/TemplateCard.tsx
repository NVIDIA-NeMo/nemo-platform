// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Badge, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import type { TemplateCardProps } from '@studio/components/CreateFilesetStart/types';
import type { FC } from 'react';

/**
 * A single ready-made recipe tile shown in the secondary area of the new-fileset view:
 * a leading icon badge above a title, description, and a use-case badge, rendered as a
 * selectable `<button>`. Mirrors {@link StartOptionCard} so the two card rows read alike.
 */
export const TemplateCard: FC<TemplateCardProps> = ({ template, selected, onSelect }) => {
  const Icon = template.icon;

  const stateClasses = selected
    ? 'cursor-pointer border-[#76b900]'
    : 'cursor-pointer border-base hover:-translate-y-0.5 hover:border-[#76b900] hover:bg-surface-hover hover:shadow-md';

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`flex h-[200px] min-w-[260px] flex-1 flex-col items-start gap-3 rounded-md border bg-surface-raised p-5 text-left transition focus-visible:border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#76b900] ${stateClasses}`}
    >
      <Flex
        align="center"
        justify="center"
        className="size-10 shrink-0 rounded-md bg-surface-sunken"
      >
        <Icon size={20} className="text-primary" aria-hidden />
      </Flex>

      <Stack gap="density-xs">
        <Text kind="body/bold/md" className="text-primary">
          {template.title}
        </Text>
        <Text kind="body/regular/sm" className="text-secondary">
          {template.description}
        </Text>
      </Stack>

      <div className="flex-1" />

      <Badge color={template.tag.color} kind={template.tag.kind}>
        {template.tag.label}
      </Badge>
    </button>
  );
};
