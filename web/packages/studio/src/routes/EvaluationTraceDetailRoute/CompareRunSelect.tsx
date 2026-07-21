// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { EvaluationSessionResponse } from '@nemo/sdk/generated/platform/schema';
import {
  DropdownContent,
  DropdownHeading,
  DropdownItem,
  DropdownRoot,
  DropdownSection,
  DropdownTrigger,
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
  /** Called with the selected run's trace_id. */
  onChange: (traceId: string) => void;
  /** Disables the trigger while the runs are loading. */
  isLoading?: boolean;
}

/**
 * Menu for picking another run of this test case to compare against. Runs are
 * grouped by evaluation so the evaluation name is shown once as a section
 * heading rather than repeated on every row. Picking a run swaps the comparison
 * column (the cap is a single compare run for now).
 */
export const CompareRunSelect: FC<CompareRunSelectProps> = ({
  runs,
  currentTraceId,
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

  return (
    <DropdownRoot>
      <DropdownTrigger
        className="min-w-[240px] justify-between"
        disabled={isLoading || isEmpty}
        aria-label="Compare against evaluation run"
      >
        {isLoading ? 'Loading…' : isEmpty ? 'No other runs' : 'Compare against evaluation run'}
      </DropdownTrigger>
      <DropdownContent align="end" className="min-w-[280px]">
        <DropdownHeading>
          <Text kind="label/bold/sm">Select a trial from a run to compare against</Text>
        </DropdownHeading>
        {groups.map(([evaluationName, evaluationRuns]) => (
          <Stack key={evaluationName}>
            <DropdownHeading>{evaluationName}</DropdownHeading>
            <DropdownSection>
              {evaluationRuns.map((run) => (
                <DropdownItem key={run.trace_id} onSelect={() => onChange(run.trace_id)}>
                  {trialLabel(run)}
                </DropdownItem>
              ))}
            </DropdownSection>
          </Stack>
        ))}
      </DropdownContent>
    </DropdownRoot>
  );
};
