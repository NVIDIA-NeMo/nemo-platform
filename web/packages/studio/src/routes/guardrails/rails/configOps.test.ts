// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import {
  findPrompt,
  hasFlow,
  stageFlows,
  withFlow,
  withoutFlow,
  withoutPrompt,
  withPrompt,
  withPromptContent,
} from '@studio/routes/guardrails/rails/configOps';

describe('flow operations', () => {
  it('appends without disturbing existing order', () => {
    const data: RailsConfig = { rails: { input: { flows: ['jailbreak detection model'] } } };

    expect(stageFlows(withFlow(data, 'input', 'self check input'), 'input')).toEqual([
      'jailbreak detection model',
      'self check input',
    ]);
  });

  it('is idempotent, so switching a rail on twice adds one flow', () => {
    const once = withFlow({}, 'input', 'self check input');
    const twice = withFlow(once, 'input', 'self check input');

    expect(stageFlows(twice, 'input')).toEqual(['self check input']);
    expect(twice).toBe(once);
  });

  it('creates the stage when the config has no rails at all', () => {
    expect(
      hasFlow(withFlow({}, 'output', 'self check output'), 'output', 'self check output')
    ).toBe(true);
  });

  it('removes only the named flow', () => {
    const data: RailsConfig = {
      rails: { input: { flows: ['self check input', 'jailbreak detection model'] } },
    };

    expect(stageFlows(withoutFlow(data, 'input', 'self check input'), 'input')).toEqual([
      'jailbreak detection model',
    ]);
  });

  it('keeps stage settings it does not own when the last flow goes', () => {
    // `parallel` belongs to the stage, not to any rail — switching the last rail off must
    // not take it with them.
    const data: RailsConfig = {
      rails: { input: { flows: ['self check input'], parallel: true } },
    };

    const result = withoutFlow(data, 'input', 'self check input');

    expect(result.rails?.input).toEqual({ flows: [], parallel: true });
  });

  it('leaves other stages untouched', () => {
    const data: RailsConfig = {
      rails: {
        input: { flows: ['self check input'] },
        output: { flows: ['self check output'] },
      },
    };

    expect(withoutFlow(data, 'input', 'self check input').rails?.output?.flows).toEqual([
      'self check output',
    ]);
  });

  it('does not mutate its input', () => {
    const data: RailsConfig = { rails: { input: { flows: ['a'] } } };
    withFlow(data, 'input', 'b');

    expect(data.rails?.input?.flows).toEqual(['a']);
  });
});

describe('prompt operations', () => {
  it('appends a new task', () => {
    const result = withPrompt({}, { task: 'self_check_input', content: 'Block?' });

    expect(result.prompts).toEqual([{ task: 'self_check_input', content: 'Block?' }]);
  });

  it('replaces an existing task in place, so prompt order is stable', () => {
    const data: RailsConfig = {
      prompts: [
        { task: 'self_check_input', content: 'Old.' },
        { task: 'self_check_output', content: 'Out.' },
      ],
    };

    const result = withPrompt(data, { task: 'self_check_input', content: 'New.' });

    expect(result.prompts).toEqual([
      { task: 'self_check_input', content: 'New.' },
      { task: 'self_check_output', content: 'Out.' },
    ]);
  });

  it('preserves fields the editor does not surface when rewriting content', () => {
    // `output_parser` and `max_tokens` come from the CLI-seeded configs; editing the
    // prompt body must not silently drop them.
    const data: RailsConfig = {
      prompts: [
        {
          task: 'content_safety_check_input $model=content_safety',
          content: 'Old.',
          output_parser: 'nemoguard_parse_prompt_safety',
          max_tokens: 50,
        },
      ],
    };

    const result = withPromptContent(
      data,
      'content_safety_check_input $model=content_safety',
      'New.'
    );

    expect(result.prompts?.[0]).toEqual({
      task: 'content_safety_check_input $model=content_safety',
      content: 'New.',
      output_parser: 'nemoguard_parse_prompt_safety',
      max_tokens: 50,
    });
  });

  it('drops the prompts list once the last entry goes', () => {
    const data: RailsConfig = { prompts: [{ task: 'self_check_input', content: 'Block?' }] };

    expect(withoutPrompt(data, 'self_check_input').prompts).toBeUndefined();
  });

  it('leaves other prompts alone', () => {
    const data: RailsConfig = {
      prompts: [
        { task: 'self_check_input', content: 'In.' },
        { task: 'self_check_output', content: 'Out.' },
      ],
    };

    expect(withoutPrompt(data, 'self_check_input').prompts).toEqual([
      { task: 'self_check_output', content: 'Out.' },
    ]);
  });

  it('finds nothing for a task the config does not have', () => {
    expect(findPrompt({}, 'self_check_input')).toBeUndefined();
  });
});
