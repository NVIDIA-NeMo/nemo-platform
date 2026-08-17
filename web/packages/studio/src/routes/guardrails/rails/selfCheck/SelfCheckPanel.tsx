// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Divider, Stack } from '@nvidia/foundations-react-core';
import { PromptScopeSection } from '@studio/routes/guardrails/rails/components/PromptScopeSection';
import { findPrompt, withPromptContent } from '@studio/routes/guardrails/rails/configOps';
import {
  SELF_CHECK_SCOPE_ORDER,
  SELF_CHECK_SCOPES,
  isSelfCheckScopeEnabled,
  setSelfCheckScopeEnabled,
} from '@studio/routes/guardrails/rails/selfCheck/bindings';
import type { RailPanelProps } from '@studio/routes/guardrails/rails/types';
import { Fragment, type FC } from 'react';

/**
 * Settings for the self-check rail: one section per stage, each with its own switch and
 * prompt. No model picker — self check runs on whichever model is already serving the
 * request.
 */
export const SelfCheckPanel: FC<RailPanelProps> = ({ data, onChange }) => (
  <Stack gap="density-xl">
    {SELF_CHECK_SCOPE_ORDER.map((scope, index) => {
      const binding = SELF_CHECK_SCOPES[scope];
      return (
        <Fragment key={scope}>
          {index > 0 ? <Divider /> : null}
          <PromptScopeSection
            scope={scope}
            enabled={isSelfCheckScopeEnabled(data, scope)}
            onEnabledChange={(enabled) => onChange(setSelfCheckScopeEnabled(data, scope, enabled))}
            prompt={findPrompt(data, binding.task)?.content ?? binding.defaultPrompt}
            onPromptChange={(content) => onChange(withPromptContent(data, binding.task, content))}
            variables={binding.variables}
          />
        </Fragment>
      );
    })}
  </Stack>
);
