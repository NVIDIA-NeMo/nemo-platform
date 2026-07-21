// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { EvaluationSessionResponse } from '@nemo/sdk/generated/platform/schema';
import {
  SelectContent,
  SelectItem,
  SelectListbox,
  SelectRoot,
  SelectTrigger,
  Spinner,
} from '@nvidia/foundations-react-core';
import { runLabel } from '@studio/routes/EvaluationTraceDetailRoute/runLabel';
import { type FC } from 'react';

interface CompareRunSelectProps {
  /** Every run of the current test case across the group's evaluations. */
  runs: EvaluationSessionResponse[];
  /** trace_id of the run shown in the primary column — excluded from the options. */
  currentTraceId: string;
  /** trace_id of the currently selected comparison run, or null when none. */
  value: string | null;
  /** Called with the selected run's trace_id. */
  onChange: (traceId: string) => void;
  /** Shows a spinner in the trigger while the runs are loading. */
  isLoading?: boolean;
}

/**
 * Dropdown that lets the user pick another run of this test case to compare against.
 * Uses Foundations select primitives directly (no react-hook-form dependency).
 */
export const CompareRunSelect: FC<CompareRunSelectProps> = ({
  runs,
  currentTraceId,
  value,
  onChange,
  isLoading = false,
}) => {
  const options = runs.filter((r) => r.trace_id !== currentTraceId);
  const isEmpty = !isLoading && options.length === 0;

  return (
    <SelectRoot value={value ?? ''} onValueChange={onChange} disabled={isEmpty}>
      <SelectTrigger
        className="min-w-[240px] border-1 nv-input"
        placeholder={isLoading ? 'Loading…' : isEmpty ? 'No other runs' : 'Compare to…'}
        slotEnd={isLoading ? <Spinner size="small" aria-label="Loading runs" /> : undefined}
        aria-label="Select a run to compare"
      />
      <SelectContent className="w-(--radix-popper-anchor-width)">
        <SelectListbox>
          {options.map((run) => (
            <SelectItem key={run.trace_id} value={run.trace_id}>
              {runLabel(run)}
            </SelectItem>
          ))}
        </SelectListbox>
      </SelectContent>
    </SelectRoot>
  );
};
