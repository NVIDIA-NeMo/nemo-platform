// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { DetectorKey } from '@studio/routes/guardrails/GuardrailConfigTab/types';

/**
 * The result of matching a configured flow name against the known built-in
 * NeMo Guardrails flows. Unrecognized (custom) flows fall back to their raw
 * name so nothing is ever hidden.
 */
export interface RecognizedFlow {
  /** Friendly label for a recognized flow, else the raw flow name. */
  label: string;
  /** The `rails.config.*` provider this flow drives, when known. */
  detectorKey?: DetectorKey;
  /** Whether the flow matched a known built-in pattern. */
  recognized: boolean;
  /** The original flow name, verbatim. */
  raw: string;
}

interface FlowPattern {
  test: RegExp;
  label: string;
  detectorKey?: DetectorKey;
}

/**
 * Recognition table for the built-in flows shipped with NeMo Guardrails.
 * Matched against the normalized flow name; first match wins, so more specific
 * patterns are listed before more general ones.
 */
const FLOW_PATTERNS: FlowPattern[] = [
  { test: /^self check facts/, label: 'Self-check facts' },
  { test: /^self check hallucination/, label: 'Self-check hallucination' },
  { test: /^self check input/, label: 'Self-check input' },
  { test: /^self check output/, label: 'Self-check output' },
  { test: /content safety (check )?input/, label: 'Content Safety', detectorKey: 'content_safety' },
  {
    test: /content safety (check )?output/,
    label: 'Content Safety',
    detectorKey: 'content_safety',
  },
  {
    test: /(llama guard|shieldgemma).*input/,
    label: 'Content Safety',
    detectorKey: 'content_safety',
  },
  {
    test: /(llama guard|shieldgemma).*output/,
    label: 'Content Safety',
    detectorKey: 'content_safety',
  },
  { test: /topic (safety|control)/, label: 'Topic Control' },
  { test: /jailbreak detection/, label: 'Jailbreak Detection', detectorKey: 'jailbreak_detection' },
  {
    test: /(mask|detect|check) sensitive data/,
    label: 'Sensitive Data',
    detectorKey: 'sensitive_data_detection',
  },
  { test: /gliner/, label: 'PII — GLiNER', detectorKey: 'gliner' },
  { test: /privateai|private ai/, label: 'PII — Private AI', detectorKey: 'privateai' },
  { test: /polygraf/, label: 'PII — Polygraf', detectorKey: 'polygraf' },
  { test: /injection detection/, label: 'Injection Detection', detectorKey: 'injection_detection' },
  {
    test: /context bloat|context manipulation/,
    label: 'Context Bloat Detection',
    detectorKey: 'context_bloat_detection',
  },
  { test: /fact check/, label: 'Fact Checking', detectorKey: 'fact_checking' },
  { test: /autoalign/, label: 'AutoAlign', detectorKey: 'autoalign' },
  { test: /patronus/, label: 'Patronus', detectorKey: 'patronus' },
  { test: /clavata/, label: 'Clavata', detectorKey: 'clavata' },
  { test: /pangea/, label: 'Pangea', detectorKey: 'pangea' },
  { test: /check blocked terms/, label: 'Blocked Terms' },
];

/**
 * Normalize a flow name for matching: lowercase, drop `$param=value` modifiers
 * (e.g. `$model=content_safety`), and collapse whitespace.
 */
export const normalizeFlowName = (flow: string): string =>
  flow.toLowerCase().replace(/\$\S+/g, ' ').replace(/\s+/g, ' ').trim();

/** Resolve a configured flow name to its friendly label and backing detector. */
export const recognizeFlow = (flow: string): RecognizedFlow => {
  const normalized = normalizeFlowName(flow);
  for (const pattern of FLOW_PATTERNS) {
    if (pattern.test.test(normalized)) {
      return {
        label: pattern.label,
        detectorKey: pattern.detectorKey,
        recognized: true,
        raw: flow,
      };
    }
  }
  return { label: flow, recognized: false, raw: flow };
};
