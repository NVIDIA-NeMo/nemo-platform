// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * Every `specSliderProps` call has to name the field its own control is bound to, and read
 * from its own backend's table.
 *
 * This is checked by reading the source because nothing else can see it. A field name that
 * belongs to a different control is still a valid string and still resolves — to another
 * field's value, or to `undefined` — so the types are satisfied, the linter is satisfied,
 * and the rendered form looks plausible. The only signal is the control's own binding.
 */

const FORM_DIR = dirname(fileURLToPath(import.meta.url));

/** `automodel.batch.micro_batch_size` → `batch_micro_batch_size`. */
const fieldForBinding = (name: string): string => {
  const [namespace, ...rest] = name.split('.');
  // `rl` binds through `training`, which is the object the RL tables are keyed off.
  return namespace === 'rl' ? rest.slice(1).join('_') : rest.join('_');
};

/**
 * `rl.*` and `grpo.*` bindings read whichever arm of the union the section renders, so the
 * file decides rather than the binding. ComputeResourcesSection is rendered by both forms;
 * the two arms inherit identical parallelism defaults, so either table is correct there.
 */
const RL_TABLES_BY_FILE: Record<string, readonly string[]> = {
  'GrpoParametersSection.tsx': ['GRPO_SPEC_DEFAULTS'],
  'GrpoAdvancedSection.tsx': ['GRPO_SPEC_DEFAULTS'],
  'DpoParametersSection.tsx': ['DPO_SPEC_DEFAULTS'],
  'GeneralParametersSection.tsx': ['DPO_SPEC_DEFAULTS'],
  'ComputeResourcesSection.tsx': ['DPO_SPEC_DEFAULTS', 'GRPO_SPEC_DEFAULTS'],
};

/** Tables a call may legitimately read, given its binding and the file it lives in. */
const allowedTables = (name: string, file: string): readonly string[] => {
  if (name.startsWith('automodel.')) return ['AUTOMODEL_SPEC_DEFAULTS'];
  if (name.startsWith('unsloth.')) return ['UNSLOTH_SPEC_DEFAULTS'];
  return RL_TABLES_BY_FILE[file] ?? [];
};

interface SliderCall {
  file: string;
  binding: string;
  table: string;
  field: string;
}

const collectSliderCalls = (): SliderCall[] => {
  const calls: SliderCall[] = [];
  for (const file of readdirSync(FORM_DIR).filter((name) => name.endsWith('.tsx'))) {
    const source = readFileSync(join(FORM_DIR, file), 'utf8');
    // One self-closing control element at a time, so a match cannot run past a control that
    // has no defaultValue and pick up its neighbour's — which is the bug this guards.
    for (const element of source.matchAll(/<Controlled\w+\b[\s\S]*?\n\s*\/>/g)) {
      const block = element[0];
      const binding = /name: '([a-z][a-z_.0-9]+)'/.exec(block);
      const call = /specSliderProps\((\w+), '([a-z_0-9]+)'\)/.exec(block);
      if (!binding || !call) continue;
      calls.push({ file, binding: binding[1], table: call[1], field: call[2] });
    }
  }
  return calls;
};

describe('customizer slider spec fields', () => {
  const calls = collectSliderCalls();

  it('finds the slider calls to check', () => {
    expect(calls.length).toBeGreaterThan(50);
  });

  it('every slider reads the field its control is bound to', () => {
    const wrong = calls
      .filter((call) => call.field !== fieldForBinding(call.binding))
      .map((call) => `${call.file}: ${call.binding} reads '${call.field}'`);
    expect(wrong).toEqual([]);
  });

  it('every slider reads a table valid for its backend and section', () => {
    const wrong = calls
      .filter((call) => !allowedTables(call.binding, call.file).includes(call.table))
      .map((call) => `${call.file}: ${call.binding} reads ${call.table}`);
    expect(wrong).toEqual([]);
  });

  /** A file the map does not know would silently exempt every call it contains. */
  it('knows the arm for every file holding an rl or grpo slider', () => {
    const unmapped = calls
      .filter((call) => /^(rl|grpo)\./.test(call.binding) && !RL_TABLES_BY_FILE[call.file])
      .map((call) => call.file);
    expect([...new Set(unmapped)]).toEqual([]);
  });
});
