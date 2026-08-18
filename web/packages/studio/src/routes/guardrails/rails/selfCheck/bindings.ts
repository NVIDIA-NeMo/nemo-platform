// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import {
  findPrompt,
  hasFlow,
  withFlow,
  withoutFlow,
  withPromptContent,
} from '@studio/routes/guardrails/rails/configOps';
import {
  SELF_CHECK_INPUT_PROMPT,
  SELF_CHECK_OUTPUT_PROMPT,
} from '@studio/routes/guardrails/rails/selfCheck/prompts';
import type { RailScope } from '@studio/routes/guardrails/rails/types';

/**
 * What the self-check rail owns in the config, per stage, and the pure operations over it.
 *
 * Separate from the rail definition so the settings panel can use it without importing
 * the definition that renders the panel.
 */

export type SelfCheckScope = Extract<RailScope, 'input' | 'output'>;

export interface SelfCheckBinding {
  /** Colang flow added to `rails.<scope>.flows`. */
  flow: string;
  /** `prompts[].task` the flow's action renders. */
  task: string;
  defaultPrompt: string;
  /** Template variables available to this stage's prompt. */
  variables: string[];
}

export const SELF_CHECK_SCOPES: Record<SelfCheckScope, SelfCheckBinding> = {
  input: {
    flow: 'self check input',
    task: 'self_check_input',
    defaultPrompt: SELF_CHECK_INPUT_PROMPT,
    variables: ['{{ user_input }}'],
  },
  output: {
    flow: 'self check output',
    task: 'self_check_output',
    defaultPrompt: SELF_CHECK_OUTPUT_PROMPT,
    variables: ['{{ bot_response }}'],
  },
};

export const SELF_CHECK_SCOPE_ORDER: SelfCheckScope[] = ['input', 'output'];

export const isSelfCheckScopeEnabled = (data: RailsConfig, scope: SelfCheckScope): boolean =>
  hasFlow(data, scope, SELF_CHECK_SCOPES[scope].flow);

/**
 * Turn one stage on or off.
 *
 * Enabling seeds the default prompt only when the task has none, so a user who tuned a
 * prompt, switched the stage off, and switched it back on gets their wording back rather
 * than the stock policy.
 */
export const setSelfCheckScopeEnabled = (
  data: RailsConfig,
  scope: SelfCheckScope,
  enabled: boolean
): RailsConfig => {
  const binding = SELF_CHECK_SCOPES[scope];
  if (!enabled) return withoutFlow(data, scope, binding.flow);
  const seeded = findPrompt(data, binding.task)
    ? data
    : withPromptContent(data, binding.task, binding.defaultPrompt);
  return withFlow(seeded, scope, binding.flow);
};
