// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { snakeCaseToTitleCase } from '@nemo/common/src/utils/formatters';
import {
  FormField,
  SegmentedControl,
  SelectContent,
  SelectItem,
  SelectListbox,
  SelectRoot,
  SelectTrigger,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import {
  EVALUATOR_PREFIX,
  STATIC_FIELDS,
  evaluatorField,
  evaluatorNameOf,
  formatSortString,
  isEvaluatorField,
  parseSortString,
} from '@studio/components/DefaultSortControl/util';
import type { FC } from 'react';

/**
 * A group's **default sort**: a single `sort`-param string (e.g. `-cost_usd.mean`) the client applies
 * as the experiments list's `sort` param on load. Always set (defaults to `-created_at`); the field
 * is any the experiments list can sort by, matching the sort/filter API grammar.
 */

export interface DefaultSortControlProps {
  value: string;
  onChange: (next: string) => void;
  /** Known evaluator names to offer as first-class options (edit modal). Empty at create time. */
  evaluatorOptions?: string[];
  disabled?: boolean;
}

export const DefaultSortControl: FC<DefaultSortControlProps> = ({
  value,
  onChange,
  evaluatorOptions = [],
  disabled,
}) => {
  const parsed = parseSortString(value);
  const setField = (field: string) => onChange(formatSortString(field, parsed.desc));

  // Keep the currently-selected evaluator selectable even if it wasn't among the discovered options
  // (e.g. a saved sort whose evaluator isn't in the sampled experiments), so it stays visible.
  const currentEvaluator = isEvaluatorField(parsed.field) ? evaluatorNameOf(parsed.field) : '';
  const evaluators =
    currentEvaluator && !evaluatorOptions.includes(currentEvaluator)
      ? [...evaluatorOptions, currentEvaluator]
      : evaluatorOptions;

  // Map a stored field to the Select's option value (static id or `evaluator:<name>`).
  const selectValueFor = (field: string): string =>
    STATIC_FIELDS.some((f) => f.value === field)
      ? field
      : `${EVALUATOR_PREFIX}${evaluatorNameOf(field)}`;

  const labelForOption = (optionValue: string): string => {
    const staticField = STATIC_FIELDS.find((f) => f.value === optionValue);
    if (staticField) return staticField.label;
    return `Avg ${snakeCaseToTitleCase(optionValue.slice(EVALUATOR_PREFIX.length))}`;
  };

  const onSelectField = (selected: string) => {
    if (selected.startsWith(EVALUATOR_PREFIX)) {
      setField(evaluatorField(selected.slice(EVALUATOR_PREFIX.length)));
    } else {
      setField(selected);
    }
  };

  return (
    <FormField slotLabel="Default sort">
      <Stack gap="density-md">
        <Text kind="body/regular/sm" className="text-secondary">
          Sets the default sort order for all users when they open this group.
        </Text>
        <div className="flex items-center gap-2">
          <SelectRoot
            value={selectValueFor(parsed.field)}
            onValueChange={onSelectField}
            disabled={disabled}
          >
            <SelectTrigger
              className="w-48"
              placeholder="Select field"
              aria-label="Sort field"
              renderValue={(v) => (typeof v === 'string' && v ? labelForOption(v) : undefined)}
            />
            <SelectContent className="w-(--radix-popper-anchor-width)">
              <SelectListbox>
                {STATIC_FIELDS.map((f) => (
                  <SelectItem key={f.value} value={f.value}>
                    {f.label}
                  </SelectItem>
                ))}
                {evaluators.map((name) => (
                  <SelectItem key={name} value={`${EVALUATOR_PREFIX}${name}`}>
                    {`Avg ${snakeCaseToTitleCase(name)}`}
                  </SelectItem>
                ))}
              </SelectListbox>
            </SelectContent>
          </SelectRoot>

          <SegmentedControl
            size="tiny"
            value={parsed.desc ? 'desc' : 'asc'}
            onValueChange={(d: string) => onChange(formatSortString(parsed.field, d === 'desc'))}
            items={[
              { value: 'asc', children: 'Asc' },
              { value: 'desc', children: 'Desc' },
            ]}
          />
        </div>
      </Stack>
    </FormField>
  );
};
