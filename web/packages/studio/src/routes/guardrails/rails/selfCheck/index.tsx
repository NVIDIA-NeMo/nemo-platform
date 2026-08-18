// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { findPrompt, withoutFlow, withoutPrompt } from '@studio/routes/guardrails/rails/configOps';
import {
  SELF_CHECK_SCOPE_ORDER,
  SELF_CHECK_SCOPES,
  isSelfCheckScopeEnabled,
  setSelfCheckScopeEnabled,
} from '@studio/routes/guardrails/rails/selfCheck/bindings';
import { SelfCheckSettings } from '@studio/routes/guardrails/rails/selfCheck/SelfCheckSettings';
import type { RailDefinition } from '@studio/routes/guardrails/rails/types';

/**
 * Self check: asks the model already answering the request to judge whether a message
 * should be blocked.
 *
 * The cheapest rail to adopt, because it needs no task model — which is why its panel has
 * no model picker, unlike content safety. What it does need is a prompt per stage: the
 * engine rejects the config if `self check input` is enabled without a `self_check_input`
 * prompt, because for an LLM-judged rail the prompt *is* the check.
 */
export const selfCheckRail: RailDefinition = {
  id: 'self-check',
  label: 'Self Checks',
  description:
    'Asks the model answering the request to judge whether a message should be blocked. Needs no separate safety model.',
  scopes: SELF_CHECK_SCOPE_ORDER,

  isEnabled: (data) => SELF_CHECK_SCOPE_ORDER.some((scope) => isSelfCheckScopeEnabled(data, scope)),

  setEnabled: (data, enabled) =>
    SELF_CHECK_SCOPE_ORDER.reduce(
      (next, scope) => setSelfCheckScopeEnabled(next, scope, enabled),
      data
    ),

  // A prompt with no flow is inert, so leaving one behind is harmless — but it is still
  // the user's text, so the list offers to discard it explicitly.
  hasStoredSettings: (data) =>
    SELF_CHECK_SCOPE_ORDER.some((scope) => findPrompt(data, SELF_CHECK_SCOPES[scope].task)),

  clearSettings: (data) =>
    SELF_CHECK_SCOPE_ORDER.reduce((next, scope) => {
      const binding = SELF_CHECK_SCOPES[scope];
      return withoutPrompt(withoutFlow(next, scope, binding.flow), binding.task);
    }, data),

  renderSettings: (props) => <SelfCheckSettings {...props} />,
};
