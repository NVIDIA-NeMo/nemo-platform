// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ChatCompletionTool } from 'openai/resources/index.mjs';

const COLUMN_TYPE_DESCRIPTION = `Each column must have "name" (string) and "column_type" (string, one of: "expression", "sampler", "llm-text", "llm-code", "llm-judge", "llm-structured", "seed-dataset", "validation", "embedding", "custom").
- expression: requires "expr" (Jinja2 only; not Python). Reference other columns only as {{ column_name }}, never bare identifiers. Do not use Python ternary forms like "1 if cond else 0" without proper Jinja wrapping and {{ }} output. Optional "dtype" ("int"|"float"|"str"|"bool"). Order columns so expr only references earlier columns. Avoid keyword substring rules for sentiment—use sampler or LLM columns instead.
- sampler: requires "sampler_type" (e.g. "uuid", "category", "uniform", "datetime", "gaussian", "poisson", "bernoulli"), and "params" (object). For "category", params: { "values": string[] }. For "uniform", params: { "low": number, "high": number }. For "uuid", params: {} or { "prefix" }. For "datetime", params: { "start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "unit"?: "D" }.
- llm-text: requires "prompt" (string), "model_alias" (string). Optional "system_prompt". Prompt may only reference columns listed earlier in "columns" (exact {{ name }} match).
- llm-code, llm-judge, llm-structured: require "prompt", "model_alias"; may have type-specific fields.
- seed-dataset, validation, embedding, custom: require type-specific fields; prefer expression/sampler/llm-text for simple specs.`;

/**
 * Tool definition for the model to call when generating a Data Designer job request.
 * Schema is aligned with PreviewRequest and DataDesignerJobRequest so the payload
 * passes API validation (avoids 422).
 */
export const generateDataDesignerJobRequestTool: ChatCompletionTool = {
  type: 'function',
  function: {
    name: 'generate_data_designer_job_request',
    description: `Generate a Data Designer job request from the user's description. Call with job_request containing a valid spec: spec.num_records (positive integer) and spec.config (object with "columns" array, at least one column). Optional: job_request.name, job_request.description, job_request.project. ${COLUMN_TYPE_DESCRIPTION} If using LLM columns, include spec.config.model_configs: array of { "alias": string, "model": string, "provider": string (required), "inference_parameters"?: { "generation_type": "chat-completion", "max_tokens"?: number } }. Each model_config MUST have "provider": the model provider name. Keep config minimal and valid for preview.`,
    parameters: {
      type: 'object',
      properties: {
        job_request: {
          type: 'object',
          description:
            'Data Designer job request: optional name, description, project; required spec with num_records and config.',
          required: ['spec'],
          properties: {
            name: {
              type: 'string',
              description:
                'Optional job name. Must not contain spaces; use hyphens or underscores (e.g. "my-data-job").',
            },
            description: { type: 'string', description: 'Optional job description.' },
            project: { type: 'string', description: 'Optional project.' },
            spec: {
              type: 'object',
              description:
                'Required. num_records (positive integer) and config (object with columns array).',
              required: ['num_records', 'config'],
              properties: {
                num_records: {
                  type: 'number',
                  description: 'Number of records to generate. Must be a positive integer.',
                  minimum: 1,
                },
                config: {
                  type: 'object',
                  description:
                    'Data Designer config. Must have "columns" (array, at least one column). Optional: model_configs.',
                  required: ['columns'],
                  properties: {
                    columns: {
                      type: 'array',
                      minItems: 1,
                      description:
                        'Column configs. Each item: name (string), column_type (string), plus type-specific fields. See main description.',
                      items: {
                        type: 'object',
                        required: ['name', 'column_type'],
                        properties: {
                          name: { type: 'string', description: 'Column name.' },
                          column_type: {
                            type: 'string',
                            enum: [
                              'expression',
                              'sampler',
                              'llm-text',
                              'llm-code',
                              'llm-judge',
                              'llm-structured',
                              'seed-dataset',
                              'validation',
                              'embedding',
                              'custom',
                            ],
                            description: 'Discriminator for column config type.',
                          },
                          drop: {
                            type: 'boolean',
                            description: 'Optional. If true, column is dropped from output.',
                          },
                          expr: {
                            type: 'string',
                            description:
                              'For column_type expression: full Jinja2 template; use {{ col }} for every column reference (not bare col). No Python if/else expressions unless expressed as Jinja {{ a if b else c }}.',
                          },
                          dtype: {
                            type: 'string',
                            enum: ['int', 'float', 'str', 'bool'],
                            description: 'For expression: result type.',
                          },
                          sampler_type: {
                            type: 'string',
                            enum: [
                              'uuid',
                              'category',
                              'subcategory',
                              'uniform',
                              'gaussian',
                              'bernoulli',
                              'bernoulli_mixture',
                              'binomial',
                              'poisson',
                              'scipy',
                              'person',
                              'person_from_faker',
                              'datetime',
                              'timedelta',
                            ],
                            description: 'For column_type sampler: sampler type.',
                          },
                          params: {
                            type: 'object',
                            description:
                              'For sampler: type-specific params. E.g. category: { values: string[] }; uniform: { low, high }; uuid: {} or { prefix }; datetime: { start, end, unit }.',
                          },
                          prompt: {
                            type: 'string',
                            description:
                              'For llm-text/llm-code/llm-judge/llm-structured: prompt template.',
                          },
                          model_alias: {
                            type: 'string',
                            description: 'For LLM columns: alias from model_configs.',
                          },
                          system_prompt: {
                            type: 'string',
                            description:
                              'Optional for LLM columns. Use to constrain style (e.g. no chain-of-thought in the answer).',
                          },
                          extract_reasoning_content: {
                            type: 'boolean',
                            description:
                              'For llm-text (and similar): if true, reasoning split by the provider goes to {column}__reasoning_content; helps when content vs reasoning are separate fields.',
                          },
                        },
                        additionalProperties: true,
                      },
                    },
                    model_configs: {
                      type: 'array',
                      description:
                        'Required if any column uses model_alias. Each item: alias, model, provider (required), optional inference_parameters.',
                      items: {
                        type: 'object',
                        required: ['alias', 'model', 'provider'],
                        properties: {
                          alias: { type: 'string' },
                          model: {
                            type: 'string',
                            description: 'Model identifier (e.g. workspace/model-name).',
                          },
                          provider: {
                            type: 'string',
                            description:
                              'Model provider name. Required. Use the provider part of the model or "workspace/provider-name" if workspace-scoped.',
                          },
                          inference_parameters: {
                            type: 'object',
                            properties: {
                              generation_type: { type: 'string', enum: ['chat-completion'] },
                              max_tokens: { type: 'number' },
                              max_parallel_requests: { type: 'number' },
                              extra_body: {
                                type: 'object',
                                description:
                                  'Provider-specific JSON merged into the chat request (e.g. flags to disable thinking mode); keys depend on the inference backend.',
                                additionalProperties: true,
                              },
                            },
                          },
                        },
                        additionalProperties: true,
                      },
                    },
                    seed_config: {
                      type: 'object',
                      description:
                        'Optional. source (e.g. seed_type, path), sampling_strategy, selection_strategy.',
                      properties: {
                        source: { type: 'object' },
                        sampling_strategy: { type: 'string', enum: ['ordered', 'shuffle'] },
                      },
                      additionalProperties: true,
                    },
                  },
                  additionalProperties: true,
                },
              },
              additionalProperties: false,
            },
          },
          additionalProperties: false,
        },
      },
      required: ['job_request'],
    },
  },
};
