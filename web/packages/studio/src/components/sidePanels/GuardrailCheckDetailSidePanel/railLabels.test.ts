// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfigOutput } from '@nemo/sdk/generated/platform/schema';
import type { RailsStatus } from '@studio/api/guardrail-checks/types';
import {
  describeRailKey,
  getActivatedGuardrails,
  humanizeRailKey,
} from '@studio/components/sidePanels/GuardrailCheckDetailSidePanel/railLabels';

describe('humanizeRailKey', () => {
  it('resolves a built-in flow to its friendly label', () => {
    expect(humanizeRailKey('self check input')).toBe('Self-check input');
  });

  it('collapses provider-specific flows onto a shared label', () => {
    expect(humanizeRailKey('content safety check input $model=content_safety')).toBe(
      'Content Safety'
    );
  });

  it('falls back to the raw name for a custom flow', () => {
    expect(humanizeRailKey('my custom rail')).toBe('my custom rail');
  });
});

describe('describeRailKey', () => {
  it('separates the input and output rails that humanizeRailKey collapses', () => {
    const input = 'content safety check input $model=content_safety';
    const output = 'content safety check output $model=content_safety';

    // The collapse this exists to undo: both are "Content Safety" on their own.
    expect(humanizeRailKey(input)).toBe(humanizeRailKey(output));
    expect(describeRailKey(input)).toBe('Content Safety (input)');
    expect(describeRailKey(output)).toBe('Content Safety (output)');
  });

  it('qualifies the other detectors that collapse across stages', () => {
    expect(describeRailKey('mask sensitive data on input')).toBe('Sensitive Data (input)');
    expect(describeRailKey('mask sensitive data on output')).toBe('Sensitive Data (output)');
    expect(describeRailKey('gliner detect pii on input')).toBe('PII — GLiNER (input)');
    expect(describeRailKey('topic safety check output $model=topic_control')).toBe(
      'Topic Control (output)'
    );
  });

  it('does not double-qualify a label that already names its stage', () => {
    expect(describeRailKey('self check input')).toBe('Self-check input');
    expect(describeRailKey('self check output')).toBe('Self-check output');
  });

  it('leaves a flow with no stage in its name unqualified', () => {
    expect(describeRailKey('jailbreak detection')).toBe('Jailbreak Detection');
  });

  it('does not double-qualify a custom flow that names its own stage', () => {
    expect(describeRailKey('my custom rail on input')).toBe('my custom rail on input');
  });
});

describe('getActivatedGuardrails', () => {
  const config: RailsConfigOutput = {
    rails: {
      input: { flows: ['content safety check input', 'jailbreak detection'] },
      output: { flows: ['content safety check output'] },
    },
  };

  it('returns [] when the config declares no rails', () => {
    expect(getActivatedGuardrails(undefined, {})).toEqual([]);
    expect(getActivatedGuardrails({}, {})).toEqual([]);
  });

  it('dedupes guardrails that share a label across stages', () => {
    // Content Safety is configured on both input and output, but is one guardrail.
    const result = getActivatedGuardrails(config, {});
    expect(result.map((g) => g.label)).toEqual(['Content Safety', 'Jailbreak Detection']);
  });

  it('marks a guardrail active only when a matching rail reported a verdict', () => {
    const railsStatus = {
      'content safety check input': { status: 'blocked' },
    } as unknown as RailsStatus;

    expect(getActivatedGuardrails(config, railsStatus)).toEqual([
      { id: 'content_safety', label: 'Content Safety', active: true },
      { id: 'jailbreak_detection', label: 'Jailbreak Detection', active: false },
    ]);
  });

  it('treats an `unknown` verdict as not activated', () => {
    const railsStatus = {
      'jailbreak detection': { status: 'unknown' },
    } as unknown as RailsStatus;

    expect(getActivatedGuardrails(config, railsStatus)).toEqual([
      { id: 'content_safety', label: 'Content Safety', active: false },
      { id: 'jailbreak_detection', label: 'Jailbreak Detection', active: false },
    ]);
  });

  it('lists a rails.config detector no flow references', () => {
    // The Config tab surfaces these; before, a detector without a matching flow
    // was invisible here, so the two tabs disagreed about what the config covers.
    const withDetectors: RailsConfigOutput = {
      rails: {
        ...config.rails,
        config: { gliner: { server_endpoint: 'http://gliner' } },
      },
    } as RailsConfigOutput;

    expect(getActivatedGuardrails(withDetectors, {}).map((g) => g.label)).toContain('PII — GLiNER');
  });

  it('collapses a guardrail declared as both a detector and a flow', () => {
    // The two sources label content safety differently; deduping on the detector
    // key rather than the label is what keeps this one row instead of two.
    const both: RailsConfigOutput = {
      rails: {
        ...config.rails,
        config: { content_safety: { server_endpoint: 'http://cs' } },
      },
    } as RailsConfigOutput;

    const contentSafety = getActivatedGuardrails(both, {}).filter((g) =>
      g.label.startsWith('Content Safety')
    );
    expect(contentSafety).toHaveLength(1);
  });

  it('marks every guardrail inactive when the check has never run', () => {
    expect(getActivatedGuardrails(config, undefined)).toEqual([
      { id: 'content_safety', label: 'Content Safety', active: false },
      { id: 'jailbreak_detection', label: 'Jailbreak Detection', active: false },
    ]);
  });

  it('gives same-labelled guardrails distinct ids', () => {
    // An unrecognized detector key and an unrecognized flow can humanize alike.
    // Deduping keeps both, so only the id is safe to use as a React key.
    const collidingLabels: RailsConfigOutput = {
      rails: {
        input: { flows: ['Acme Guard'] },
        config: { acme_guard: {} },
      },
    } as unknown as RailsConfigOutput;

    const result = getActivatedGuardrails(collidingLabels, {});
    expect(result.map((g) => g.label)).toEqual(['Acme Guard', 'Acme Guard']);
    expect(new Set(result.map((g) => g.id)).size).toBe(result.length);
  });

  it('lists configured coverage the run never exercised', () => {
    // The point of sourcing from the config: a guardrail absent from rails_status
    // still appears, dimmed, rather than vanishing.
    const railsStatus = {
      'content safety check input': { status: 'success' },
    } as unknown as RailsStatus;

    const result = getActivatedGuardrails(config, railsStatus);
    expect(result).toContainEqual({
      id: 'jailbreak_detection',
      label: 'Jailbreak Detection',
      active: false,
    });
  });
});
