// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { EvaluationResponse } from '@nemo/sdk/generated/platform/schema';
import {
  SelectContent,
  SelectItem,
  SelectListbox,
  SelectRoot,
  SelectTrigger,
  Spinner,
} from '@nvidia/foundations-react-core';
import { type FC } from 'react';

interface CompareExperimentSelectProps {
  /** All sibling evaluations eligible for comparison (already filtered to same dataset). */
  evaluations: EvaluationResponse[];
  /** Name of the primary evaluation — excluded from the option list. */
  currentEvaluationName: string;
  /** Currently selected comparison evaluation name, or null when none is selected. */
  value: string | null;
  /** Called when the user picks a new evaluation to compare against. */
  onChange: (evaluationName: string) => void;
  /** Shows a spinner in the trigger while the evaluations list is loading. */
  isLoading?: boolean;
}

/**
 * Dropdown that lets the user pick a sibling evaluation to compare against.
 * Uses Foundations select primitives directly (no react-hook-form dependency).
 */
export const CompareExperimentSelect: FC<CompareExperimentSelectProps> = ({
  evaluations,
  currentEvaluationName,
  value,
  onChange,
  isLoading = false,
}) => {
  const options = evaluations.filter((e) => e.name !== currentEvaluationName);
  const isEmpty = !isLoading && options.length === 0;

  return (
    <SelectRoot value={value ?? ''} onValueChange={onChange} disabled={isEmpty}>
      <SelectTrigger
        className="min-w-[200px] border-1 nv-input"
        placeholder={isLoading ? 'Loading…' : isEmpty ? 'No comparable evaluations' : 'Compare to…'}
        slotEnd={isLoading ? <Spinner size="small" aria-label="Loading evaluations" /> : undefined}
        aria-label="Select evaluation to compare"
      />
      <SelectContent className="w-(--radix-popper-anchor-width)">
        <SelectListbox>
          {options.map((evaluation) => (
            <SelectItem key={evaluation.name} value={evaluation.name}>
              {evaluation.name}
            </SelectItem>
          ))}
        </SelectListbox>
      </SelectContent>
    </SelectRoot>
  );
};
