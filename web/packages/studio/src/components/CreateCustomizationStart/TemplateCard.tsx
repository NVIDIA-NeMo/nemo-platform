// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Badge, Button, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import type { TemplateCardProps } from '@studio/components/CreateCustomizationStart/types';
import { KeyRound, Trash2 } from 'lucide-react';
import type { FC } from 'react';

/**
 * One template tile, used for both shipped recipes and the user's own saved templates.
 *
 * A delete control, when present, is a sibling of the selecting `<button>` rather than a
 * child: a button inside a button is invalid HTML and the inner click gets swallowed.
 */
export const TemplateCard: FC<TemplateCardProps> = ({ model, selected, onSelect }) => {
  const stateClasses = !model.applicable
    ? 'cursor-not-allowed border-base opacity-60'
    : selected
      ? 'cursor-pointer border-[#76b900]'
      : 'cursor-pointer border-base hover:-translate-y-0.5 hover:border-[#76b900] hover:bg-surface-hover hover:shadow-md';

  return (
    <div className="relative">
      <button
        type="button"
        onClick={model.applicable ? onSelect : undefined}
        aria-pressed={model.applicable ? selected : undefined}
        aria-disabled={!model.applicable}
        className={`flex h-[184px] w-full flex-col items-start gap-2 overflow-hidden rounded-md border bg-surface-raised p-4 text-left transition focus-visible:border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#76b900] ${
          model.onDelete ? 'pr-11' : ''
        } ${stateClasses}`}
      >
        <Text kind="label/regular/sm" className="text-secondary">
          {model.publisher}
        </Text>

        <Stack gap="density-xs" className="min-h-0">
          <Text kind="body/bold/md" className="text-primary">
            {model.title}
          </Text>
          {model.description ? (
            <Text
              kind="body/regular/sm"
              className="line-clamp-2 text-secondary"
              title={model.description}
            >
              {model.description}
            </Text>
          ) : null}
        </Stack>

        <div className="flex-1" />

        {!model.applicable ? (
          <Text kind="body/regular/sm" className="text-placeholder">
            Saved by a different version of Studio — cannot be applied.
          </Text>
        ) : null}

        <Flex align="center" gap="density-xs" wrap="wrap">
          {model.badges.map((badge) => (
            <Badge key={badge.label} color={badge.color} kind="outline" size="small">
              {badge.label}
            </Badge>
          ))}
          {model.requiresHfToken ? (
            <Flex align="center" gap="density-xs" className="text-placeholder">
              <KeyRound size={12} aria-hidden />
              <Text kind="label/regular/sm">HF token</Text>
            </Flex>
          ) : null}
        </Flex>

        {model.footer?.map((line) => (
          <Text
            key={line}
            kind="label/regular/sm"
            className="truncate text-placeholder"
            title={line}
          >
            {line}
          </Text>
        ))}
      </button>

      {model.onDelete ? (
        <Flex className="absolute right-2 top-2">
          <Button
            kind="tertiary"
            size="tiny"
            disabled={model.isDeleting}
            aria-label={`Delete template ${model.title}`}
            onClick={model.onDelete}
          >
            <Trash2 size={14} aria-hidden />
          </Button>
        </Flex>
      ) : null}
    </div>
  );
};
