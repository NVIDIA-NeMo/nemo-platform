// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Default seed questions — short, recognizable LLM "gotchas" that make
 * cross-model differences obvious in the first prompt.
 *
 * Lives in its own module (not co-located with the SeedQuestions component)
 * so the component file can stay a pure component export and not trip
 * `react-refresh/only-export-components`. Named with the `default` prefix
 * to avoid a case-only filename collision with `SeedQuestions.tsx` on
 * case-insensitive filesystems (macOS).
 */
export const DEFAULT_SEED_QUESTIONS = [
  "How many 'r's are in the word strawberry?",
  "Mary's mom has 4 kids: April, May, and June. Who is the fourth kid?",
];
