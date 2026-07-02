// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SamplerType } from '@nemo/sdk/generated/data-designer/schema';
import type { ColumnTypeColor, ColumnTypeGroup } from '@studio/components/AddColumnPalette/types';
import {
  Activity,
  Binary,
  Bot,
  Braces,
  CalendarDays,
  ChartBarBig,
  ChartLine,
  ChartSpline,
  CodeXml,
  Database,
  Dices,
  Hash,
  Image,
  LayoutGrid,
  ListTree,
  MessageSquare,
  Network,
  Scale,
  ShieldCheck,
  SquareFunction,
  Timer,
  ToggleLeft,
  User,
} from 'lucide-react';

/** Accent color → Tailwind text color utility for an option's icon. */
export const ICON_COLOR_CLASS: Record<ColumnTypeColor, string> = {
  blue: 'text-accent-blue',
  gray: 'text-accent-gray',
  green: 'text-accent-green',
  purple: 'text-accent-purple',
  red: 'text-accent-red',
  teal: 'text-accent-teal',
  yellow: 'text-accent-yellow',
};

/**
 * The Data Designer column catalog, grouped for the "Add a column" palette.
 *
 * Mirrors the column types documented at
 * https://docs.nvidia.com/nemo/datadesigner/concepts/columns — Sampler is its own
 * group with every sampler sub-type broken out; generation, transform, validation, and
 * data/custom columns follow. `columnType`/`samplerType` use the canonical SDK literals.
 */
export const COLUMN_TYPE_GROUPS: ColumnTypeGroup[] = [
  {
    id: 'sampler',
    label: 'Sampler',
    options: [
      {
        id: 'sampler.uuid',
        columnType: 'sampler',
        samplerType: SamplerType.uuid,
        label: 'UUID',
        description: 'Unique identifiers',
        icon: Hash,
        color: 'gray',
      },
      {
        id: 'sampler.category',
        columnType: 'sampler',
        samplerType: SamplerType.category,
        label: 'Category',
        description: 'Weighted categorical values',
        icon: LayoutGrid,
        color: 'gray',
      },
      {
        id: 'sampler.subcategory',
        columnType: 'sampler',
        samplerType: SamplerType.subcategory,
        label: 'Subcategory',
        description: 'Hierarchical categories',
        icon: ListTree,
        color: 'gray',
      },
      {
        id: 'sampler.uniform',
        columnType: 'sampler',
        samplerType: SamplerType.uniform,
        label: 'Uniform',
        description: 'Evenly distributed numbers',
        icon: ChartBarBig,
        color: 'gray',
      },
      {
        id: 'sampler.gaussian',
        columnType: 'sampler',
        samplerType: SamplerType.gaussian,
        label: 'Gaussian',
        description: 'Normally distributed values',
        icon: ChartSpline,
        color: 'gray',
      },
      {
        id: 'sampler.bernoulli',
        columnType: 'sampler',
        samplerType: SamplerType.bernoulli,
        label: 'Bernoulli',
        description: 'Binary outcomes',
        icon: ToggleLeft,
        color: 'gray',
      },
      {
        id: 'sampler.bernoulli_mixture',
        columnType: 'sampler',
        samplerType: SamplerType.bernoulli_mixture,
        label: 'Bernoulli Mixture',
        description: 'Mixed binary components',
        icon: Binary,
        color: 'gray',
      },
      {
        id: 'sampler.binomial',
        columnType: 'sampler',
        samplerType: SamplerType.binomial,
        label: 'Binomial',
        description: 'Successes in n trials',
        icon: Dices,
        color: 'gray',
      },
      {
        id: 'sampler.poisson',
        columnType: 'sampler',
        samplerType: SamplerType.poisson,
        label: 'Poisson',
        description: 'Event counts & frequencies',
        icon: Activity,
        color: 'gray',
      },
      {
        id: 'sampler.scipy',
        columnType: 'sampler',
        samplerType: SamplerType.scipy,
        label: 'Scipy',
        description: 'Any scipy.stats distribution',
        icon: ChartLine,
        color: 'gray',
      },
      {
        id: 'sampler.person',
        columnType: 'sampler',
        samplerType: SamplerType.person,
        label: 'Person',
        description: 'Synthetic people & demographics',
        icon: User,
        color: 'gray',
      },
      {
        id: 'sampler.datetime',
        columnType: 'sampler',
        samplerType: SamplerType.datetime,
        label: 'Datetime',
        description: 'Timestamps in a range',
        icon: CalendarDays,
        color: 'gray',
      },
      {
        id: 'sampler.timedelta',
        columnType: 'sampler',
        samplerType: SamplerType.timedelta,
        label: 'Timedelta',
        description: 'Time durations',
        icon: Timer,
        color: 'gray',
      },
    ],
  },
  {
    id: 'generate',
    label: 'Generate',
    options: [
      {
        id: 'llm-text',
        columnType: 'llm-text',
        label: 'LLM-Text',
        description: 'Free-form text from a prompt',
        icon: MessageSquare,
        color: 'blue',
      },
      {
        id: 'llm-code',
        columnType: 'llm-code',
        label: 'LLM-Code',
        description: 'Code in 15+ languages',
        icon: CodeXml,
        color: 'green',
      },
      {
        id: 'llm-structured',
        columnType: 'llm-structured',
        label: 'LLM-Structured',
        description: 'JSON to a schema',
        icon: Braces,
        color: 'purple',
      },
      {
        id: 'llm-judge',
        columnType: 'llm-judge',
        label: 'LLM-Judge',
        description: 'Score content 0–N',
        icon: Scale,
        color: 'yellow',
      },
      {
        id: 'image',
        columnType: 'image',
        label: 'Image',
        description: 'Images from text prompts',
        icon: Image,
        color: 'purple',
      },
      {
        id: 'embedding',
        columnType: 'embedding',
        label: 'Embedding',
        description: 'Vector embeddings',
        icon: Network,
        color: 'blue',
      },
    ],
  },
  {
    id: 'transform',
    label: 'Transform',
    options: [
      {
        id: 'expression',
        columnType: 'expression',
        label: 'Expression',
        description: 'Jinja2 transform · no LLM',
        icon: SquareFunction,
        color: 'green',
      },
    ],
  },
  {
    id: 'validate',
    label: 'Validate',
    options: [
      {
        id: 'validation',
        columnType: 'validation',
        label: 'Validation',
        description: 'Check against rules',
        icon: ShieldCheck,
        color: 'red',
      },
    ],
  },
  {
    id: 'data',
    label: 'Data & custom',
    options: [
      {
        id: 'seed-dataset',
        columnType: 'seed-dataset',
        label: 'Seed Dataset',
        description: 'Bootstrap from a file',
        icon: Database,
        color: 'gray',
      },
      {
        id: 'custom',
        columnType: 'custom',
        label: 'Custom',
        description: 'Python function logic',
        icon: Bot,
        color: 'gray',
      },
    ],
  },
];
