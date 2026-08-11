// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DEFAULT_SEED_QUESTIONS } from '@studio/components/chat/defaultSeedQuestions';
import { PromptSuggestionPills } from '@studio/components/PromptSuggestionPills';
import type { PromptSuggestion } from '@studio/components/PromptSuggestionPills/types';
import { type FC, type ReactNode, useMemo } from 'react';

interface SeedQuestionsProps {
  questions?: string[];
  onSelect: (prompt: string) => void;
  /** Mirrors the composer's disabled state, so a seed can't target a dead composer. */
  disabled?: boolean;
  /** Rendered bottom-aligned at the leading end of the row (e.g. metrics). */
  slotStart?: ReactNode;
  /** Rendered bottom-aligned at the trailing end of the row. */
  slotEnd?: ReactNode;
}

/**
 * Seed questions for the chat composer: a row of {@link PromptSuggestionPills} flanked by
 * optional slots for metrics and composer actions. A seed question is its own label, so it
 * maps to a suggestion whose label and prompt are the same string.
 */
export const SeedQuestions: FC<SeedQuestionsProps> = ({
  questions = DEFAULT_SEED_QUESTIONS,
  onSelect,
  disabled,
  slotStart,
  slotEnd,
}) => {
  const suggestions = useMemo<PromptSuggestion[]>(
    () => questions.map((question) => ({ label: question, prompt: question })),
    [questions]
  );

  return (
    <div className="flex items-start gap-2">
      {slotStart && <div className="shrink-0 self-end">{slotStart}</div>}
      <PromptSuggestionPills
        suggestions={suggestions}
        onSelect={onSelect}
        disabled={disabled}
        className="flex-1"
      />
      {slotEnd && <div className="shrink-0 self-end">{slotEnd}</div>}
    </div>
  );
};
