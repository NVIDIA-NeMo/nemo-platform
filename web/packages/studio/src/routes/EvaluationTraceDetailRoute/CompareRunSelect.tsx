// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { TextInputSpinner } from '@nemo/common/src/components/form/TextInputSpinner';
import type { EvaluationSessionResponse } from '@nemo/sdk/generated/platform/schema';
import {
  DropdownHeading,
  DropdownSection,
  SelectContent,
  SelectItem,
  SelectListbox,
  SelectRoot,
  SelectTrigger,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { trialLabel } from '@studio/routes/EvaluationTraceDetailRoute/runLabel';
import { type FC, useMemo } from 'react';

interface CompareRunSelectProps {
  /** Every run of the current test case across the group's evaluations. */
  runs: EvaluationSessionResponse[];
  /** trace_id of the run shown in the primary column — never offered as an option. */
  currentTraceId: string;
  /** trace_id of the currently selected comparison run, or null when none. */
  value: string | null;
  /** Called with the selected run's trace_id. */
  onChange: (traceId: string) => void;
  /** Keeps the control disabled with a loading placeholder until the runs resolve. */
  isLoading?: boolean;
}

/**
 * Select for picking another run of this test case to compare against. Runs are
 * grouped by evaluation so the evaluation name shows once as a section heading
 * rather than repeating on every row. Picking a run swaps the comparison column
 * (the cap is a single compare run for now); the trigger label stays fixed.
 */
export const CompareRunSelect: FC<CompareRunSelectProps> = ({
  runs,
  currentTraceId,
  value,
  onChange,
  isLoading = false,
}) => {
  const groups = useMemo(() => {
    const byEvaluation = new Map<string, EvaluationSessionResponse[]>();
    for (const run of runs) {
      if (run.trace_id === currentTraceId) continue;
      const existing = byEvaluation.get(run.evaluation_name);
      if (existing) existing.push(run);
      else byEvaluation.set(run.evaluation_name, [run]);
    }
    return [...byEvaluation.entries()];
  }, [runs, currentTraceId]);

  const isEmpty = groups.length === 0;
  const disabled = isLoading || isEmpty;
  const label = isLoading
    ? 'Loading other runs'
    : isEmpty
      ? 'No runs to compare to'
      : 'Compare against evaluation run';

  return (
    <SelectRoot value={value ?? undefined} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger
        className={`min-w-[240px] border-1 ${disabled ? 'nv-input-disabled' : 'nv-input'}`}
        placeholder={label}
        // Keep the trigger label fixed instead of echoing the selected run.
        renderValue={() => label}
        slotEnd={isLoading ? <TextInputSpinner /> : undefined}
        aria-label="Compare against evaluation run"
      />
      <SelectContent className="w-(--radix-popper-anchor-width)">
        <SelectListbox>
          <DropdownHeading>
            <Text kind="label/bold/sm">Select a trial from a run to compare against</Text>
          </DropdownHeading>
          <Stack className="max-h-[320px] w-full overflow-auto">
            {groups.map(([evaluationName, evaluationRuns]) => (
              <DropdownSection key={evaluationName}>
                <DropdownHeading>{evaluationName}</DropdownHeading>
                {evaluationRuns.map((run) => (
                  <SelectItem key={run.trace_id} value={run.trace_id}>
                    {trialLabel(run)}
                  </SelectItem>
                ))}
              </DropdownSection>
            ))}
          </Stack>
        </SelectListbox>
      </SelectContent>
    </SelectRoot>
  );
};
