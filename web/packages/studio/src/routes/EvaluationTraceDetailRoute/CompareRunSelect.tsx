// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { EvaluationSessionResponse } from '@nemo/sdk/generated/platform/schema';
import {
  DropdownHeading,
  SelectContent,
  SelectItem,
  SelectListbox,
  SelectRoot,
  SelectTrigger,
  Text,
} from '@nvidia/foundations-react-core';
import { runLabel, trialLabel } from '@studio/routes/EvaluationTraceDetailRoute/runLabel';
import { Fragment, type FC, useMemo } from 'react';

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
        aria-label="Compare against evaluation run"
      />
      <SelectContent className="w-(--radix-popper-anchor-width)">
        <SelectListbox density="compact">
          <DropdownHeading className="pb-density-sm">
            <Text kind="label/regular/sm" className="text-secondary">
              Select a trial from a run to compare against
            </Text>
          </DropdownHeading>
          {/* Block (not flex) container so long headings keep their height instead of
              being shrunk and vertically clipped when the list overflows. */}
          <div className="max-h-[360px] w-full overflow-y-auto">
            {groups.map(([evaluationName, evaluationRuns]) =>
              evaluationRuns.length === 1 ? (
                // Single trial: collapse run + trial onto one selectable line.
                <SelectItem
                  key={evaluationRuns[0].trace_id}
                  value={evaluationRuns[0].trace_id}
                  aria-label={runLabel(evaluationRuns[0])}
                >
                  <Text kind="label/bold/sm">{runLabel(evaluationRuns[0])}</Text>
                </SelectItem>
              ) : (
                <Fragment key={evaluationName}>
                  <DropdownHeading>
                    <Text kind="label/regular/sm" className="text-secondary">
                      {evaluationName}
                    </Text>
                  </DropdownHeading>
                  {evaluationRuns.map((run) => (
                    <SelectItem
                      key={run.trace_id}
                      value={run.trace_id}
                      // Screen readers get the full "<evaluation> · Trial XXXXX"; the
                      // visible label stays "Trial XXXXX" indented under the heading.
                      aria-label={runLabel(run)}
                    >
                      {/* Indent the content (not the item) — SelectItem's own padding
                          wins over a className on the item itself. */}
                      <Text kind="label/bold/sm" className="pl-density-lg">
                        <span className="text-secondary font-normal" aria-hidden>
                          ↳{' '}
                        </span>
                        {trialLabel(run)}
                      </Text>
                    </SelectItem>
                  ))}
                </Fragment>
              )
            )}
          </div>
        </SelectListbox>
      </SelectContent>
    </SelectRoot>
  );
};
