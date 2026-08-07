// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FILESET_TEMPLATES } from '@studio/components/CreateFilesetStart/templates';
import type { StartOption } from '@studio/components/CreateFilesetStart/types';
import { LayoutGrid, Plus, Sparkles } from 'lucide-react';

/** "N recipe(s)" badge label, kept in sync with the number of authored templates. */
const RECIPE_COUNT_LABEL = `${FILESET_TEMPLATES.length} ${
  FILESET_TEMPLATES.length === 1 ? 'recipe' : 'recipes'
}`;

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
