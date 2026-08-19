// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import type { ActivatedGuardrail, RailsStatus } from '@studio/api/guardrail-checks/types';
import {
  detectorMeta,
  listConfiguredDetectors,
} from '@studio/routes/guardrails/GuardrailConfigTab/detectors';
import {
  normalizeFlowName,
  recognizeFlow,
} from '@studio/routes/guardrails/GuardrailConfigTab/flowRegistry';

/**
 * Friendly label for a key of a run's `rails_status` map. The keys are flow
 * names, so they resolve through the same registry the config tab uses;
 * unrecognized flows fall back to their raw name.
 *
 * Deliberately many-to-one: a detector's input and output flows collapse onto a
 * single guardrail name. Use this where a guardrail is counted once (coverage);
 * use [[describeRailKey]] where individual rails are listed.
 */
export const humanizeRailKey = (key: string): string => recognizeFlow(key).label;

/**
 * The stage a flow ran at, read off the flow name.
 *
 * Only input and output are listed: those are the stages real flow names spell
 * out, and the only ones observed to collide. A flow at a `retrieval` or
 * `tool_input` stage whose name says "input" reads as input — less precise, but
 * never wrong. Add a pattern here if a flow name ever names those stages.
 *
 * Sourced from the name rather than the config's `rails.<stage>.flows` because
 * run history spans config versions: the config on hand may no longer describe
 * the rails an older run executed, and RunHistoryTab has no config at all.
 */
const STAGE_PATTERNS: { test: RegExp; stage: string }[] = [
  { test: /\binput\b/, stage: 'input' },
  { test: /\boutput\b/, stage: 'output' },
];

/**
 * Friendly label for a rail, qualified by the stage it ran at.
 *
 * Without the qualifier a config running one detector on both input and output
 * renders two rows reading "Content Safety" with different verdicts and no way
 * to tell them apart — the stage is exactly what `humanizeRailKey` discards.
 * Labels that already name their stage ("Self-check input") are left alone.
 */
export const describeRailKey = (key: string): string => {
  const label = humanizeRailKey(key);
  const normalized = normalizeFlowName(key);
  const stage = STAGE_PATTERNS.find(({ test }) => test.test(normalized))?.stage;
  return !stage || label.toLowerCase().includes(stage) ? label : `${label} (${stage})`;
};

/**
 * Every flow configured on a guardrail config, across the flow-bearing stages.
 * Dialog and action rails are excluded — the SDK schema gives them no `flows`.
 */
const collectConfigFlows = (data: RailsConfig | undefined): string[] => {
  const rails = data?.rails;
  if (!rails) return [];
  return [
    ...(rails.input?.flows ?? []),
    ...(rails.output?.flows ?? []),
    ...(rails.retrieval?.flows ?? []),
    ...(rails.tool_input?.flows ?? []),
    ...(rails.tool_output?.flows ?? []),
  ];
};

// Declared alongside RunRecord — it is persisted on each run, not just rendered.
export type { ActivatedGuardrail };

/**
 * Identity for deduping a guardrail: its detector key when the flow registry
 * knows one, else the friendly label.
 *
 * Keying on the detector is what lets a `rails.config.*` entry and the flow that
 * drives it collapse into one row even when their labels differ — the detector
 * catalog calls it "Sensitive Data (Presidio)" where the flow registry says
 * "Sensitive Data".
 */
const guardrailId = (flow: string): string => {
  const { detectorKey, label } = recognizeFlow(flow);
  return detectorKey ?? label;
};

/**
 * Every guardrail the config declares, each marked active when a rail resolving
 * to it reported a verdict in the run. One that never reported (or reported
 * `unknown`) reads as inactive — the distinction the indicator dots draw.
 *
 * Two sources are unioned, because a config can declare a guardrail either way:
 * the `rails.config.*` detectors (the same list, in the same order, that the
 * Config tab shows) and the flows referenced by the flow-bearing stages. Dialog
 * and action rails contribute nothing — the SDK schema gives them no `flows`.
 *
 * Deriving from the *config* rather than from `rails_status` is what makes the
 * section meaningful: it surfaces coverage the run never exercised, which a
 * run-only view cannot.
 */
export const getActivatedGuardrails = (
  data: RailsConfig | undefined,
  railsStatus: RailsStatus | undefined
): ActivatedGuardrail[] => {
  const ran = new Set(
    Object.entries(railsStatus ?? {})
      .filter(([, rail]) => rail.status !== 'unknown')
      .map(([key]) => guardrailId(key))
  );

  const seen = new Set<string>();
  const result: ActivatedGuardrail[] = [];
  const add = (id: string, label: string) => {
    if (seen.has(id)) return;
    seen.add(id);
    result.push({ id, label, active: ran.has(id) });
  };

  for (const key of listConfiguredDetectors(data?.rails)) {
    add(key, detectorMeta(key).label);
  }
  for (const flow of collectConfigFlows(data)) {
    add(guardrailId(flow), recognizeFlow(flow).label);
  }
  return result;
};
