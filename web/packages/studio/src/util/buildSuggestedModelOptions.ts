// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { SelectItemOption } from '@nemo/common/src/components/form/ControlledSearchableSelect';

const EXCLUDED_TERMS = ['llama', 'safety', 'safeguard', 'embed', 'vl', 'reward', 'parse'];

const isSuggested = (name: string): boolean => {
  const lower = name.toLowerCase();
  if (EXCLUDED_TERMS.some((term) => lower.includes(term))) return false;
  return lower.includes('nvidia') && lower.includes('nemotron');
};

export interface ModelListEntry {
  name: string;
}

export const SUGGESTED_MODEL_GROUP_LABELS = {
  suggested: 'Suggested',
  all: 'All Models',
} as const;

/**
 * Build the option set for the Studio model picker with a Suggested / All split.
 * Suggested = NVIDIA Nemotron models, excluding llama/safety/embed/vl/reward/parse
 * variants. Same model can appear in both groups; the picker dedupes by composite
 * key, so the Suggested row stays clickable.
 */
export const buildSuggestedModelOptions = (models: ModelListEntry[]): SelectItemOption[] => {
  const base = models.map((m) => ({ value: m.name, label: m.name }));
  const suggested = base
    .filter((o) => isSuggested(o.value))
    .map((o) => ({ ...o, group: 'suggested' as const }));
  const all = base.map((o) => ({ ...o, group: 'all' as const }));
  return [...suggested, ...all];
};

// Not chat LLMs — must never be auto-selected as an agent's LLM.
const NON_LLM_TERMS = ['embed', 'rerank', 'reward', 'safeguard', 'safety', 'parse', 'vl', 'guard'];

const isLlmCandidate = (name: string): boolean => {
  const lower = name.toLowerCase();
  return !NON_LLM_TERMS.some((term) => lower.includes(term));
};

export const pickDefaultModelName = (models: ModelListEntry[]): string | undefined => {
  const names = models.map((m) => m.name);
  return names.find(isSuggested) ?? names.find(isLlmCandidate);
};
