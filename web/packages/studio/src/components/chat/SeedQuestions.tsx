// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Text } from '@nvidia/foundations-react-core';
import { DEFAULT_SEED_QUESTIONS } from '@studio/components/chat/defaultSeedQuestions';
import { type FC } from 'react';

interface SeedQuestionsProps {
  questions?: string[];
  onSelect: (prompt: string) => void;
  label?: string;
  /** Compare layout uses rounded chips without a section label. */
  variant?: 'default' | 'compare';
}

/**
 * Row of bordered chip buttons that float just above the composer. Each
 * question is its own distinct, clickable affordance — same border + radius
 * as the composer card so they read as a related control family, but
 * detached so they feel like floating action chips, not inline text.
 */
export const SeedQuestions: FC<SeedQuestionsProps> = ({
  questions = DEFAULT_SEED_QUESTIONS,
  onSelect,
  label,
  variant = 'default',
}) => {
  const isCompare = variant === 'compare';
  const chipClassName = isCompare
    ? 'cursor-pointer rounded-lg border border-base bg-surface-raised px-3 py-2 text-sm text-fg-base transition-colors hover:border-emphasis hover:bg-surface-sunken'
    : 'cursor-pointer rounded-full border border-base bg-surface-base px-3 py-1.5 text-xs text-fg-base transition-colors hover:border-emphasis hover:bg-surface-sunken';

  return (
    <div className="flex flex-col gap-2">
      {label && !isCompare ? (
        <Text kind="label/regular/sm" color="secondary">
          {label}
        </Text>
      ) : null}
      <div className="flex flex-wrap items-start gap-2">
        {questions.map((q) => (
          <button key={q} type="button" onClick={() => onSelect(q)} className={chipClassName}>
            {q}
          </button>
        ))}
      </div>
    </div>
  );
};
