// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsOutput } from '@nemo/sdk/generated/platform/schema';
import type { RunRecord } from '@studio/api/guardrail-checks/types';
import { buildRailRows } from '@studio/routes/guardrails/GuardrailCheckDetailRoute/railRows';

const rails: RailsOutput = {
  input: { flows: ['content safety input', 'jailbreak detection'] },
  output: { flows: ['content safety output'] },
  retrieval: { flows: ['retrieval check'] },
};

const run = (rails_status: RunRecord['rails_status']): RunRecord => ({
  run_at: '2026-07-15T00:00:00Z',
  status: 'blocked',
  rails_status,
});

describe('buildRailRows', () => {
  it('lists all configured flows in input → output → retrieval order', () => {
    const rows = buildRailRows(rails, undefined);
    expect(rows.map((r) => r.name)).toEqual([
      'content safety input',
      'jailbreak detection',
      'content safety output',
      'retrieval check',
    ]);
  });

  it('marks every rail skipped when there is no run', () => {
    const rows = buildRailRows(rails, undefined);
    expect(rows.every((r) => r.verdict === 'skipped')).toBe(true);
  });

  it('maps run status to allowed / guarded / skipped', () => {
    const rows = buildRailRows(
      rails,
      run({
        'content safety input': { status: 'success' },
        'content safety output': { status: 'blocked' },
        // jailbreak detection + retrieval check absent -> skipped
      })
    );
    const byName = Object.fromEntries(rows.map((r) => [r.name, r.verdict]));
    expect(byName).toEqual({
      'content safety input': 'allowed',
      'jailbreak detection': 'skipped',
      'content safety output': 'guarded',
      'retrieval check': 'skipped',
    });
  });

  it('de-dupes a flow name that appears in multiple rail sections', () => {
    const dupeRails: RailsOutput = {
      input: { flows: ['shared flow'] },
      output: { flows: ['shared flow'] },
    };
    const rows = buildRailRows(dupeRails, undefined);
    expect(rows).toHaveLength(1);
    expect(rows[0].name).toBe('shared flow');
  });

  it('returns an empty list when no rails are configured', () => {
    expect(buildRailRows(undefined, undefined)).toEqual([]);
    expect(buildRailRows({}, undefined)).toEqual([]);
  });
});
