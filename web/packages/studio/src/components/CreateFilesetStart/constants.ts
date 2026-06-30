// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { StartOption } from '@studio/components/CreateFilesetStart/types';
import { Copy, LayoutGrid, Plus, Sparkles } from 'lucide-react';

/**
 * The "How do you want to start?" tiles, in display order. Only "Build from scratch"
 * is enabled today; the others are placeholders for upcoming entry points.
 */
export const START_OPTIONS: StartOption[] = [
  {
    id: 'ai',
    title: 'Describe with AI',
    description:
      'Tell us what you need in plain language. AI drafts the columns and prompts — then you refine everything visually.',
    icon: Sparkles,
    tag: { label: 'Recommended', color: 'green', kind: 'solid' },
    enabled: false,
  },
  {
    id: 'template',
    title: 'Start from a template',
    description: 'Pick a ready-made recipe for SFT, classification, RAG eval, tool-use and more.',
    icon: LayoutGrid,
    tag: { label: '8 recipes', color: 'blue', kind: 'outline' },
    enabled: false,
  },
  {
    id: 'clone',
    title: 'Clone a fileset',
    description: 'Reuse the recipe from a fileset you already built. Tweak the columns and re-run.',
    icon: Copy,
    tag: { label: 'From your library', color: 'purple', kind: 'outline' },
    enabled: false,
  },
  {
    id: 'scratch',
    title: 'Build from scratch',
    description: 'Open an empty canvas and add columns block by block, your way.',
    icon: Plus,
    tag: { label: 'Blank', color: 'gray', kind: 'outline' },
    enabled: true,
  },
];
