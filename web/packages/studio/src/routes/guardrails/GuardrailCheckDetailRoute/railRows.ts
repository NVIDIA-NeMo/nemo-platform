// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsOutput } from '@nemo/sdk/generated/platform/schema';
import type { RunRecord } from '@studio/api/guardrail-checks/types';

/** How a single configured rail resolved on the most recent run. */
export type RailVerdict = 'allowed' | 'guarded' | 'skipped';

export interface RailRow {
  /** Flow name as configured on the parent config. */
  name: string;
  verdict: RailVerdict;
}

/**
 * Build the rail list for the detail view: every flow configured on the parent
 * config (input → output → retrieval, de-duped, order preserved), resolved
 * against the latest run's per-rail status.
 *
 * - rail ran + passed  → "allowed"
 * - rail ran + blocked → "guarded"
 * - rail not present in the run (or no run at all) → "skipped"
 */
export const buildRailRows = (
  rails: RailsOutput | undefined,
  run: RunRecord | undefined
): RailRow[] => {
  const flowNames = [
    ...(rails?.input?.flows ?? []),
    ...(rails?.output?.flows ?? []),
    ...(rails?.retrieval?.flows ?? []),
  ];

  const seen = new Set<string>();
  const rows: RailRow[] = [];
  for (const name of flowNames) {
    if (seen.has(name)) continue;
    seen.add(name);

    const status = run?.rails_status?.[name]?.status;
    const verdict: RailVerdict =
      status === 'blocked' ? 'guarded' : status === 'success' ? 'allowed' : 'skipped';
    rows.push({ name, verdict });
  }
  return rows;
};
