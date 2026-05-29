// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { type FC } from 'react';

/** Default seed questions — short, recognizable LLM "gotchas" that make
 *  cross-model differences obvious in the first prompt. */
export const DEFAULT_SEED_QUESTIONS = [
  "How many 'r's are in the word strawberry?",
  "Mary's mom has 4 kids: April, May, and June. Who is the fourth kid?",
];

interface SeedQuestionsProps {
  questions?: string[];
  onSelect: (prompt: string) => void;
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
}) => {
  return (
    <div className="flex flex-wrap items-start gap-2">
      {questions.map((q) => (
        <button
          key={q}
          type="button"
          onClick={() => onSelect(q)}
          className="cursor-pointer rounded-md border border-base bg-surface-base px-3 py-1.5 text-xs text-fg-base transition-colors hover:border-emphasis hover:bg-surface-sunken"
        >
          {q}
        </button>
      ))}
    </div>
  );
};
