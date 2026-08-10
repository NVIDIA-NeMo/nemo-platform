// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FILESET_TEMPLATES } from '@studio/components/CreateFilesetStart/templates';
import type { PromptSuggestion, StartOption } from '@studio/components/CreateFilesetStart/types';
import { LayoutGrid, Plus, Sparkles } from 'lucide-react';

/** "N recipe(s)" badge label, kept in sync with the number of authored templates. */
const RECIPE_COUNT_LABEL = `${FILESET_TEMPLATES.length} ${
  FILESET_TEMPLATES.length === 1 ? 'recipe' : 'recipes'
}`;

/**
 * Example prompts offered as pills over an empty prompt field. Each is a complete,
 * generation-ready description — the pill label is only the shorthand for it.
 */
export const PROMPT_SUGGESTIONS: PromptSuggestion[] = [
  {
    label: 'Phishing email triage',
    prompt:
      '200 customer support emails for training a phishing triage agent, each labelled as phishing or legitimate, with a short reason for the label and the sender domain. Sampled across categories (billing, returns, tech support) with subcategories per category (billing: overcharge, failed payment; returns: damaged item, wrong size)',
  },
  {
    label: 'Support ticket routing',
    prompt:
      '100 inbound customer support tickets for training a triage agent. Each row has the raw ticket text as the customer wrote it, the queue it should route to (billing, shipping, technical, account cancellation), an urgency level (P1 to P4) and a one-line summary. Include ambiguous tickets that plausibly span two queues, and a few where the customer threatens to churn',
  },
  {
    label: 'Refund policy Q&A',
    prompt:
      '50 evaluation examples for a customer-facing refund policy assistant. Each row has a passage from a returns and refunds policy, a question a real customer would ask, the answer grounded in that passage, and whether the policy actually covers the situation. Include questions the policy does not answer, marked as out of scope',
  },
];

export const START_OPTIONS: StartOption[] = [
  {
    id: 'ai',
    title: 'Describe with AI',
    description:
      'Tell us what you need in plain language. AI drafts the columns and prompts — then you refine everything visually.',
    icon: Sparkles,
    enabled: true,
  },
  {
    id: 'template',
    title: 'Start from a template',
    description: 'Pick a ready-made recipe for SFT, classification, RAG eval, tool-use and more.',
    icon: LayoutGrid,
    tag: { label: RECIPE_COUNT_LABEL, color: 'blue', kind: 'outline' },
    enabled: true,
  },
  {
    id: 'scratch',
    title: 'Build from scratch',
    description: 'Open an empty canvas and add columns block by block, your way.',
    icon: Plus,
    enabled: true,
  },
];
