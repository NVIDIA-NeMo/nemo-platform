// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Output formats a dataset can be rewritten into, shared by every transform
 * surface: the Data Designer job transform and the in-place file transform.
 *
 * A format is purely a Studio-side convenience: it names the fields the target
 * consumer expects and pre-fills the template the transform actually receives.
 * Anything a format cannot express is still reachable through the `custom`
 * format, which is the raw key/template grid.
 */

/** One mappable field in an output format. */
export interface OutputFormatField {
  /**
   * Dot path into the output record. Numeric segments build arrays, so
   * `messages.0.content` produces `{ messages: [{ content: ... }] }`.
   */
  readonly path: string;
  readonly label: string;
  readonly description: string;
  readonly required: boolean;
  /** Source column-name fragments used to guess a mapping, best match first. */
  readonly hints: readonly string[];
  /**
   * Marks a field that must be unique per row. When no source column matches,
   * the transform job generates one instead of leaving it unmapped — a constant
   * would be identical on every row, which silently collapses the output.
   */
  readonly identity?: boolean;
}

export interface OutputFormat {
  readonly id: string;
  readonly label: string;
  readonly description: string;
  /** Default name of the processor, and of the directory its output is written to. */
  readonly defaultProcessorName: string;
  readonly fields: readonly OutputFormatField[];
  /** Literal values emitted at fixed paths — not user-mappable (e.g. a chat role). */
  readonly constants?: Readonly<Record<string, string>>;
}

export const CUSTOM_FORMAT_ID = 'custom';

export const OUTPUT_FORMATS: readonly OutputFormat[] = [
  {
    id: 'agent-eval-task',
    label: 'Evaluation Tasks',
    description: 'Tasks the Evaluator can run an agent against.',
    defaultProcessorName: 'agent_eval_tasks',
    fields: [
      {
        path: 'id',
        label: 'id',
        description: 'Stable task identifier, unique within the task collection.',
        required: true,
        hints: ['task_id', 'id', 'uuid'],
        identity: true,
      },
      {
        path: 'intent',
        label: 'intent',
        description: 'Human-readable description of the desired agent behavior.',
        required: true,
        hints: ['intent', 'goal', 'objective', 'category', 'topic'],
      },
      {
        path: 'inputs.instruction',
        label: 'inputs.instruction',
        description: 'The task input handed to the agent.',
        required: true,
        hints: ['instruction', 'prompt', 'question', 'request', 'input'],
      },
      {
        path: 'reference.expected',
        label: 'reference.expected',
        description: 'Grader-only ground truth. Never shown to the agent.',
        required: false,
        hints: ['expected', 'reference', 'answer', 'response', 'ideal'],
      },
    ],
  },
  {
    id: 'chat-messages',
    label: 'Messages',
    description: 'A two-turn messages array, the usual shape for SFT.',
    defaultProcessorName: 'chat_messages',
    fields: [
      {
        path: 'messages.0.content',
        label: 'user message',
        description: 'Content of the user turn.',
        required: true,
        hints: ['prompt', 'question', 'instruction', 'request', 'input'],
      },
      {
        path: 'messages.1.content',
        label: 'assistant message',
        description: 'Content of the assistant turn.',
        required: true,
        hints: ['response', 'answer', 'completion', 'output', 'ideal'],
      },
    ],
    constants: {
      'messages.0.role': 'user',
      'messages.1.role': 'assistant',
    },
  },
  {
    id: CUSTOM_FORMAT_ID,
    label: 'Custom',
    description: 'Write the output schema yourself, one key at a time.',
    defaultProcessorName: 'transformed',
    fields: [],
  },
];

export const findOutputFormat = (id: string): OutputFormat | undefined =>
  OUTPUT_FORMATS.find((format) => format.id === id);
