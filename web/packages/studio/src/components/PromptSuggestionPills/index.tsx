// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Button, Flex } from '@nvidia/foundations-react-core';
import type { PromptSuggestionPillsProps } from '@studio/components/PromptSuggestionPills/types';
import classNames from 'classnames';
import type { FC } from 'react';

/**
 * Row of bordered chip buttons, each writing a ready-made prompt into a nearby field.
 * Shared by the chat composer's seed questions and the "Describe with AI" prompt field so
 * the two read as one control family; the label is a shorthand, the prompt is what lands
 * in the field, and the two are the same string when there is nothing to shorten.
 */
export const PromptSuggestionPills: FC<PromptSuggestionPillsProps> = ({
  suggestions,
  onSelect,
  disabled,
  className,
}) => (
  <Flex className={classNames('w-full min-w-0 gap-2', className)} wrap="wrap" justify="start">
    {suggestions.map((suggestion) => (
      <Button
        key={suggestion.label}
        type="button"
        kind="secondary"
        size="tiny"
        disabled={disabled}
        onClick={() => onSelect(suggestion.prompt)}
        className="cursor-pointer rounded-full border border-base bg-surface-base px-3 py-1.5 text-xs text-secondary transition-colors hover:border-interaction-hover hover:bg-surface-sunken hover:text-primary disabled:pointer-events-none disabled:border-disabled disabled:text-disabled"
      >
        {suggestion.label}
      </Button>
    ))}
  </Flex>
);
