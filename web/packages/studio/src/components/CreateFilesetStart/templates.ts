// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SamplerType } from '@nemo/sdk/generated/data-designer/schema';
import type { FilesetTemplate } from '@studio/components/CreateFilesetStart/types';
import { DEFAULT_BUILD_MODEL_NAME } from '@studio/constants/constants';
import { FlaskConical, GraduationCap } from 'lucide-react';

/**
 * The ready-made recipes shown as cards in the secondary area when "Start from a
 * template" is selected. One recipe today; add entries here as more are authored —
 * the card grid and selection flow scale to any number without further changes.
 */
export const FILESET_TEMPLATES: FilesetTemplate[] = [
  {
    id: 'sft-instruction',
    title: 'Instruction fine-tuning (SFT)',
    description:
      'Instruction–response pairs for supervised fine-tuning: a sampled topic, an LLM-generated user instruction, and a model answer.',
    icon: GraduationCap,
    tag: { label: 'Fine-tuning', color: 'blue', kind: 'outline' },
    columns: [
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'domain',
        values: {
          values:
            'science, technology, history, arts, business, health, education, sports, travel, cooking',
        },
      },
      {
        columnType: 'llm-text',
        name: 'instruction',
        values: {
          prompt:
            'Write a single, self-contained user instruction about {{ domain }}. Return only the instruction.',
          model_alias: 'default',
        },
      },
      {
        columnType: 'llm-text',
        name: 'response',
        values: {
          prompt:
            'Respond helpfully and concisely to the following instruction:\n\n{{ instruction }}',
          model_alias: 'default',
        },
      },
    ],
    models: [{ alias: 'default', model: DEFAULT_BUILD_MODEL_NAME }],
  },
  {
    id: 'sampler-showcase',
    title: 'All samplers (showcase)',
    description:
      'A column for each previewable sampler sub-type — UUID, category, subcategory, uniform, gaussian, Bernoulli, Bernoulli mixture, binomial, Poisson, scipy, datetime, and timedelta — seeded with valid params for QA.',
    icon: FlaskConical,
    tag: { label: 'Showcase', color: 'green', kind: 'outline' },
    columns: [
      {
        columnType: 'sampler',
        samplerType: SamplerType.uuid,
        name: 'uuid_id',
        values: { prefix: 'user-', short_form: 'true', uppercase: 'false' },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'category_topic',
        values: { values: 'science, technology, arts', weights: '3, 2, 1' },
      },
      {
        // Parent-category reference → draws an edge from `category_topic`.
        columnType: 'sampler',
        samplerType: SamplerType.subcategory,
        name: 'subcategory_topic',
        values: {
          category: 'category_topic',
          values:
            '{ "science": ["physics", "biology"], "technology": ["ai", "systems"], "arts": ["music", "painting"] }',
        },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.uniform,
        name: 'uniform_score',
        values: { low: '0', high: '1', decimal_places: '3' },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.gaussian,
        name: 'gaussian_measure',
        values: { mean: '100', stddev: '15', decimal_places: '2' },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.bernoulli,
        name: 'bernoulli_flag',
        values: { p: '0.3' },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.bernoulli_mixture,
        name: 'bernoulli_mixture_value',
        values: { p: '0.5', dist_name: 'norm', dist_params: '{ "loc": 10, "scale": 2 }' },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.binomial,
        name: 'binomial_successes',
        values: { n: '10', p: '0.5' },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.poisson,
        name: 'poisson_events',
        values: { mean: '4' },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.scipy,
        name: 'scipy_sample',
        values: { dist_name: 'beta', dist_params: '{ "a": 2, "b": 5 }', decimal_places: '3' },
      },
      // The managed `person` sampler is intentionally omitted: it requires downloaded
      // Nemotron Personas datasets, so it can't preview in environments without them.
      {
        columnType: 'sampler',
        samplerType: SamplerType.datetime,
        name: 'created_at',
        values: { start: '2020-01-01', end: '2024-01-01', unit: 'D' },
      },
      {
        // Reference-datetime column → draws an edge from `created_at`.
        columnType: 'sampler',
        samplerType: SamplerType.timedelta,
        name: 'shipped_after',
        values: { dt_min: '1', dt_max: '30', reference_column_name: 'created_at', unit: 'D' },
      },
    ],
  },
];

export const findTemplate = (id: string): FilesetTemplate | undefined =>
  FILESET_TEMPLATES.find((template) => template.id === id);
