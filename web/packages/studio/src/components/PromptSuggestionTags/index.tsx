// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, Tag } from '@nvidia/foundations-react-core';
import type { PromptSuggestionTagsProps } from '@studio/components/PromptSuggestionTags/types';
import classNames from 'classnames';
import type { FC } from 'react';

/**
 * Row of outline Tags, each writing a ready-made prompt into a nearby field.
 * Shared by the chat composer's seed questions and the "Describe with AI" prompt field so
 * the two read as one control family; the label is a shorthand, the prompt is what lands
 * in the field, and the two are the same string when there is nothing to shorten.
 */
export const PromptSuggestionTags: FC<PromptSuggestionTagsProps> = ({
  suggestions,
  onSelect,
  disabled,
  className,
}) => (
  <Flex className={classNames('w-full min-w-0 gap-2', className)} wrap="wrap" justify="start">
    {suggestions.map((suggestion) => (
      <Tag
        key={suggestion.label}
        color="gray"
        kind="outline"
        disabled={disabled}
        onClick={() => onSelect(suggestion.prompt)}
      >
        {suggestion.label}
      </Tag>
    ))}
  </Flex>
);
