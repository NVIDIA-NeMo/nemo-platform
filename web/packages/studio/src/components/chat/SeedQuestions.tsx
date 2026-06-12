// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DEFAULT_SEED_QUESTIONS } from '@studio/components/chat/defaultSeedQuestions';
import { type FC, type ReactNode } from 'react';

interface SeedQuestionsProps {
  questions?: string[];
  onSelect: (prompt: string) => void;
  /** Rendered bottom-aligned at the leading end of the row (e.g. metrics). */
  slotStart?: ReactNode;
  /** Rendered bottom-aligned at the trailing end of the row. */
  slotEnd?: ReactNode;
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
  slotStart,
  slotEnd,
}) => {
  return (
    <div className="flex items-start gap-2">
      {slotStart && <div className="shrink-0 self-end">{slotStart}</div>}
      <div className="flex min-w-0 flex-1 flex-wrap items-start gap-2">
        {questions.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => onSelect(q)}
            className="cursor-pointer rounded-full border border-base bg-surface-base px-3 py-1.5 text-xs text-fg-base transition-colors hover:border-emphasis hover:bg-surface-sunken"
          >
            {q}
          </button>
        ))}
      </div>
      {slotEnd && <div className="shrink-0 self-end">{slotEnd}</div>}
    </div>
  );
};
