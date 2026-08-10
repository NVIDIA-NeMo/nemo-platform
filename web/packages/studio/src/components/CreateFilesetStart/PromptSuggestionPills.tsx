// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, Tag } from '@nvidia/foundations-react-core';
import type { PromptSuggestionPillsProps } from '@studio/components/CreateFilesetStart/types';
import type { FC } from 'react';

/**
 * Row of example-prompt tags that floats over the bottom of the prompt field. Positioned
 * absolutely so it reads as an affordance on the empty textarea rather than another control
 * below it; the parent hides the whole row once the field has content, so the tags never
 * cover what the user typed.
 */
export const PromptSuggestionPills: FC<PromptSuggestionPillsProps> = ({
  suggestions,
  onSelect,
}) => (
  <Flex gap="density-sm" wrap="wrap" className="pointer-events-none absolute inset-x-3 bottom-3">
    {suggestions.map((suggestion) => (
      <Tag
        key={suggestion.label}
        type="button"
        color="gray"
        kind="outline"
        density="compact"
        onClick={() => onSelect(suggestion.prompt)}
        className="pointer-events-auto cursor-pointer bg-surface-raised transition-colors hover:border-interaction-hover hover:bg-interaction-hover active:bg-accent-gray-subtle-hover"
      >
        {suggestion.label}
      </Tag>
    ))}
  </Flex>
);
