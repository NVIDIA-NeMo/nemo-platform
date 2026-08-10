// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  normalizeFlowName,
  recognizeFlow,
} from '@studio/routes/guardrails/GuardrailConfigTab/flowRegistry';

describe('normalizeFlowName', () => {
  it('lowercases, strips $param modifiers, and collapses whitespace', () => {
    expect(normalizeFlowName('Content Safety Check Input $model=content_safety')).toBe(
      'content safety check input'
    );
    expect(normalizeFlowName('  jailbreak   detection  ')).toBe('jailbreak detection');
  });
});

describe('recognizeFlow', () => {
  it('maps built-in content safety flows to the content_safety detector', () => {
    const result = recognizeFlow('content safety check input $model=content_safety');
    expect(result.recognized).toBe(true);
    expect(result.label).toBe('Content Safety');
    expect(result.detectorKey).toBe('content_safety');
    expect(result.raw).toBe('content safety check input $model=content_safety');
  });

  it('maps jailbreak and sensitive-data flows to their detectors', () => {
    expect(recognizeFlow('jailbreak detection').detectorKey).toBe('jailbreak_detection');
    expect(recognizeFlow('mask sensitive data on input').detectorKey).toBe(
      'sensitive_data_detection'
    );
  });

  it('recognizes prompt-based self checks without a backing detector', () => {
    const result = recognizeFlow('self check input');
    expect(result.recognized).toBe(true);
    expect(result.label).toBe('Self-check input');
    expect(result.detectorKey).toBeUndefined();
  });

  it('falls back to the raw name for unknown custom flows', () => {
    const result = recognizeFlow('my custom guardrail');
    expect(result.recognized).toBe(false);
    expect(result.label).toBe('my custom guardrail');
    expect(result.detectorKey).toBeUndefined();
    expect(result.raw).toBe('my custom guardrail');
  });
});
