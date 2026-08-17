// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import { findPrompt } from '@studio/routes/guardrails/rails/configOps';
import { selfCheckRail } from '@studio/routes/guardrails/rails/selfCheck';
import { setSelfCheckScopeEnabled } from '@studio/routes/guardrails/rails/selfCheck/bindings';
import {
  SELF_CHECK_INPUT_PROMPT,
  SELF_CHECK_OUTPUT_PROMPT,
} from '@studio/routes/guardrails/rails/selfCheck/prompts';

/**
 * The engine rejects a config where a flow is enabled without the prompt its action
 * renders, so these pin the flow/prompt pairing the switch is responsible for.
 */
describe('selfCheckRail.setEnabled', () => {
  it('adds both flows and seeds both prompts', () => {
    const result = selfCheckRail.setEnabled({}, true);

    expect(result.rails?.input?.flows).toEqual(['self check input']);
    expect(result.rails?.output?.flows).toEqual(['self check output']);
    expect(findPrompt(result, 'self_check_input')?.content).toBe(SELF_CHECK_INPUT_PROMPT);
    expect(findPrompt(result, 'self_check_output')?.content).toBe(SELF_CHECK_OUTPUT_PROMPT);
  });

  it('never enables a flow without the prompt its action needs', () => {
    const enabled = selfCheckRail.setEnabled({}, true);

    for (const [scope, task] of [
      ['input', 'self_check_input'],
      ['output', 'self_check_output'],
    ] as const) {
      const hasFlow = (enabled.rails?.[scope]?.flows ?? []).length > 0;
      expect(hasFlow).toBe(Boolean(findPrompt(enabled, task)));
    }
  });

  it('switching off stops the rail but keeps the tuned prompt', () => {
    const tuned = { ...selfCheckRail.setEnabled({}, true) };
    const edited = setSelfCheckScopeEnabled(tuned, 'input', true);
    const withCustomPrompt: RailsConfig = {
      ...edited,
      prompts: edited.prompts?.map((prompt) =>
        prompt.task === 'self_check_input' ? { ...prompt, content: 'My policy.' } : prompt
      ),
    };

    const off = selfCheckRail.setEnabled(withCustomPrompt, false);

    expect(off.rails?.input?.flows).toEqual([]);
    expect(off.rails?.output?.flows).toEqual([]);
    expect(findPrompt(off, 'self_check_input')?.content).toBe('My policy.');
  });

  it('restores the tuned prompt rather than the default when switched back on', () => {
    const on = selfCheckRail.setEnabled({}, true);
    const tuned: RailsConfig = {
      ...on,
      prompts: on.prompts?.map((prompt) =>
        prompt.task === 'self_check_input' ? { ...prompt, content: 'My policy.' } : prompt
      ),
    };

    const roundTripped = selfCheckRail.setEnabled(selfCheckRail.setEnabled(tuned, false), true);

    expect(findPrompt(roundTripped, 'self_check_input')?.content).toBe('My policy.');
  });

  it('leaves other rails in the config alone', () => {
    const data: RailsConfig = {
      models: [{ type: 'content_safety', engine: 'nim', model: 'system/nemoguard' }],
      rails: { input: { flows: ['content safety check input $model=content_safety'] } },
      prompts: [{ task: 'content_safety_check_input $model=content_safety', content: 'Safe?' }],
    };

    const result = selfCheckRail.setEnabled(data, true);

    expect(result.rails?.input?.flows).toEqual([
      'content safety check input $model=content_safety',
      'self check input',
    ]);
    expect(result.models).toEqual(data.models);
    expect(findPrompt(result, 'content_safety_check_input $model=content_safety')).toBeDefined();
  });

  it('adds no task model, because self check runs on the request’s own model', () => {
    expect(selfCheckRail.setEnabled({}, true).models).toBeUndefined();
  });
});

describe('selfCheckRail.isEnabled', () => {
  it('is true when either stage is running', () => {
    expect(selfCheckRail.isEnabled(setSelfCheckScopeEnabled({}, 'input', true))).toBe(true);
    expect(selfCheckRail.isEnabled(setSelfCheckScopeEnabled({}, 'output', true))).toBe(true);
  });

  it('is false for a config that only has the prompts', () => {
    const promptsOnly = selfCheckRail.setEnabled(selfCheckRail.setEnabled({}, true), false);

    expect(selfCheckRail.isEnabled(promptsOnly)).toBe(false);
  });
});

describe('selfCheckRail.clearSettings', () => {
  it('removes the prompts that switching off deliberately kept', () => {
    const off = selfCheckRail.setEnabled(selfCheckRail.setEnabled({}, true), false);
    expect(selfCheckRail.hasStoredSettings(off)).toBe(true);

    const cleared = selfCheckRail.clearSettings(off);

    expect(selfCheckRail.hasStoredSettings(cleared)).toBe(false);
    expect(cleared.prompts).toBeUndefined();
  });

  it('reports nothing to discard for a config that never used the rail', () => {
    expect(selfCheckRail.hasStoredSettings({})).toBe(false);
  });
});
