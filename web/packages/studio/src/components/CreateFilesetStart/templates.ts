// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SamplerType } from '@nemo/sdk/generated/data-designer/schema';
import type { FilesetTemplate } from '@studio/components/CreateFilesetStart/types';
import { DEFAULT_BUILD_MODEL_NAME, DEFAULT_EMBEDDER_MODEL_NAME } from '@studio/constants/constants';
import {
  Braces,
  Code2,
  FlaskConical,
  GraduationCap,
  Scale,
  SearchCode,
  SquareFunction,
} from 'lucide-react';

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
  {
    id: 'code-generation',
    title: 'Code generation + validation (Python)',
    description:
      'Python coding challenges with LLM-generated solutions and automatic code validation: exercises a sampled topic, an LLM task description, a code answer, and a pass/fail validation column.',
    icon: Code2,
    tag: { label: 'Fine-tuning', color: 'green', kind: 'outline' },
    columns: [
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'topic',
        values: {
          values:
            'sorting algorithms, string manipulation, file I/O, data structures, recursion, decorators, generators, async I/O',
        },
      },
      {
        columnType: 'llm-text',
        name: 'task',
        values: {
          prompt:
            'Write a clear, self-contained Python coding challenge about {{ topic }}. State what the function should do and give one example input/output pair. Return only the problem statement.',
          model_alias: 'default',
        },
      },
      {
        columnType: 'llm-code',
        name: 'solution',
        values: {
          prompt:
            'Solve the following Python coding challenge. Return only the code — no prose, no markdown fences.\n\n{{ task }}',
          model_alias: 'default',
          code_lang: 'python',
        },
      },
      {
        columnType: 'validation',
        name: 'is_valid',
        values: {
          target_columns: 'solution',
          validator_type: 'code',
          validator_params: '{ "code_lang": "python" }',
        },
      },
    ],
    models: [{ alias: 'default', model: DEFAULT_BUILD_MODEL_NAME }],
  },
  {
    id: 'structured-extraction',
    title: 'Structured data extraction',
    description:
      'Free-form text paired with its structured JSON representation — for training extraction and information-retrieval models. An LLM writes a description; a second call extracts it into a typed schema.',
    icon: Braces,
    tag: { label: 'Fine-tuning', color: 'purple', kind: 'outline' },
    columns: [
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'entity_type',
        values: {
          values: 'product, company, research paper, recipe, event, film',
        },
      },
      {
        columnType: 'llm-text',
        name: 'description',
        values: {
          prompt:
            'Write a realistic, detailed description of a {{ entity_type }} — include concrete names, dates, and figures. Return only the description.',
          model_alias: 'default',
        },
      },
      {
        columnType: 'llm-structured',
        name: 'structured',
        values: {
          prompt:
            'Extract the key attributes from the following {{ entity_type }} description:\n\n{{ description }}\n\nReturn the attributes as a JSON object.',
          model_alias: 'default',
          output_format:
            '{ "type": "object", "properties": { "name": { "type": "string" }, "attributes": { "type": "object" } }, "required": ["name", "attributes"] }',
        },
      },
    ],
    models: [{ alias: 'default', model: DEFAULT_BUILD_MODEL_NAME }],
  },
  {
    id: 'preference-pairs',
    title: 'Preference pairs (reward modeling)',
    description:
      'An instruction with a high-quality chosen answer, a lower-quality rejected answer, and an LLM judge score — for DPO fine-tuning and reward model training.',
    icon: Scale,
    tag: { label: 'Alignment', color: 'yellow', kind: 'outline' },
    columns: [
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'topic',
        values: {
          values: 'science, history, philosophy, mathematics, literature, technology, ethics',
        },
      },
      {
        columnType: 'llm-text',
        name: 'instruction',
        values: {
          prompt:
            'Write a challenging, open-ended question about {{ topic }} that requires an explanatory answer. Return only the question.',
          model_alias: 'default',
        },
      },
      {
        columnType: 'llm-text',
        name: 'chosen',
        values: {
          prompt: 'Answer the following question accurately and thoroughly:\n\n{{ instruction }}',
          model_alias: 'default',
        },
      },
      {
        columnType: 'llm-text',
        name: 'rejected',
        values: {
          prompt:
            'Give a brief, vague, or slightly inaccurate answer to the following question — do not correct yourself:\n\n{{ instruction }}',
          model_alias: 'default',
        },
      },
      {
        columnType: 'llm-judge',
        name: 'quality_score',
        values: {
          prompt:
            'On a scale of 1–5 (1 = very poor, 5 = excellent), rate the quality of the following answer.\n\nQuestion: {{ instruction }}\nAnswer: {{ chosen }}\n\nReturn only the integer score.',
          model_alias: 'default',
          scores:
            '[{ "name": "Quality", "description": "Overall answer quality.", "options": { "1": "Very poor", "5": "Excellent" } }]',
        },
      },
    ],
    models: [{ alias: 'default', model: DEFAULT_BUILD_MODEL_NAME }],
  },
  {
    id: 'semantic-search',
    title: 'Semantic search dataset',
    description:
      'Query–passage pairs with vector embeddings for retrieval, RAG evaluation, and semantic similarity benchmarks. Requires an embedding model configured under the "embedder" alias.',
    icon: SearchCode,
    tag: { label: 'Retrieval', color: 'blue', kind: 'outline' },
    columns: [
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'domain',
        values: {
          values: 'science, technology, health, finance, culture, sports',
        },
      },
      {
        columnType: 'llm-text',
        name: 'passage',
        values: {
          prompt:
            'Write a factual, self-contained paragraph about a specific topic within {{ domain }}. Return only the paragraph.',
          model_alias: 'default',
        },
      },
      {
        columnType: 'llm-text',
        name: 'query',
        values: {
          prompt:
            'Write a short search query that a user might type to retrieve the following passage:\n\n{{ passage }}\n\nReturn only the query.',
          model_alias: 'default',
        },
      },
      {
        columnType: 'embedding',
        name: 'passage_embedding',
        values: {
          target_column: 'passage',
          model_alias: 'embedder',
        },
      },
    ],
    models: [
      { alias: 'default', model: DEFAULT_BUILD_MODEL_NAME },
      {
        alias: 'embedder',
        model: DEFAULT_EMBEDDER_MODEL_NAME,
        inferenceParams: {
          generation_type: 'embedding',
          encoding_format: 'float',
          extra_body: { input_type: 'passage', truncate: 'NONE' },
        },
      },
    ],
  },
  {
    id: 'expression-transforms',
    title: 'Expression transforms (no LLM)',
    description:
      'Derived columns computed via Jinja2 expressions — full-name concatenation, score banding into letter grades. No LLM calls; previews instantly.',
    icon: SquareFunction,
    tag: { label: 'Transform', color: 'teal', kind: 'outline' },
    columns: [
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'first_name',
        values: { values: 'Alice, Bob, Carol, Dave, Eve, Frank, Grace, Hank' },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.category,
        name: 'last_name',
        values: { values: 'Smith, Jones, Williams, Brown, Davis, Miller' },
      },
      {
        columnType: 'sampler',
        samplerType: SamplerType.uniform,
        name: 'score',
        values: { low: '0', high: '100', decimal_places: '1' },
      },
      {
        columnType: 'expression',
        name: 'full_name',
        values: {
          expr: '{{ first_name }} {{ last_name }}',
        },
      },
      {
        columnType: 'expression',
        name: 'grade',
        values: {
          expr: '{% if score|float >= 90 %}A{% elif score|float >= 80 %}B{% elif score|float >= 70 %}C{% elif score|float >= 60 %}D{% else %}F{% endif %}',
          dtype: 'str',
        },
      },
    ],
  },
];

export const findTemplate = (id: string): FilesetTemplate | undefined =>
  FILESET_TEMPLATES.find((template) => template.id === id);
