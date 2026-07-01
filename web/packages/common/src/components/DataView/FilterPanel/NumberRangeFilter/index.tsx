// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  isNumberRangeFilter,
  type NumberRangeFilterValue,
} from '@nemo/common/src/components/DataView/FilterPanel/NumberRangeFilter/util';
import type { DataViewColumn } from '@nemo/common/src/components/DataView/FilterPanel/types';
import { Flex, RangeSlider, Stack, TextInput } from '@nvidia/foundations-react-core';
import { useCallback, useEffect, useState, type KeyboardEvent } from 'react';

const DEFAULT_BOUNDS = { min: 0, max: 100, step: 1 };

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

/**
 * Numeric range filter control. Pairs a {@link RangeSlider} (top row) with two
 * {@link TextInput} fields (min / max, in a {@link Flex} row) and stores its
 * value as `{ $gte, $lte }` via the column's filter state.
 *
 * The slider and the inputs are two views of the same range: dragging a thumb
 * updates the inputs live, while typing a bound previews on the slider and
 * commits on blur / Enter. Bounds are ordered before being stored, so an
 * inverted entry (min > max) is normalized rather than emitted as an impossible
 * range. A bound is only emitted when it actually narrows the track, so the
 * applied filter reads as `{ $gte }`, `{ $lte }`, both, or clears at the extremes.
 *
 * Use with {@link numberRangeFilter} in a column's `meta.filter`.
 */
export function NumberRangeFilterControl({ column }: { column: DataViewColumn }) {
  const filterDef = column.columnDef.meta?.filter;
  const { min, max, step } = isNumberRangeFilter(filterDef) ? filterDef : DEFAULT_BOUNDS;
  const header = column.columnDef.header;
  const label = filterDef?.label ?? (typeof header === 'string' ? header : column.id);

  const committed = column.getFilterValue() as NumberRangeFilterValue | undefined;
  const committedLower = committed?.$gte ?? min;
  const committedUpper = committed?.$lte ?? max;

  // Local string state lets users edit each field freely — including clearing it
  // or typing partial values like "1." — without snapping back on every keystroke.
  const [minText, setMinText] = useState(String(committedLower));
  const [maxText, setMaxText] = useState(String(committedUpper));

  const parseBound = useCallback(
    (text: string, fallback: number): number => {
      const trimmed = text.trim();
      if (trimmed === '') return fallback;
      const parsed = Number(trimmed);
      return Number.isFinite(parsed) ? clamp(parsed, min, max) : fallback;
    },
    [min, max]
  );

  // Resync inputs when the committed value changes externally (an applied-filter
  // chip being removed, a reset, a slider release). Skip when the field already
  // parses to the committed value so in-progress typing is never clobbered.
  useEffect(() => {
    setMinText((curr) =>
      parseBound(curr, min) === committedLower ? curr : String(committedLower)
    );
  }, [committedLower, parseBound, min]);
  useEffect(() => {
    setMaxText((curr) =>
      parseBound(curr, max) === committedUpper ? curr : String(committedUpper)
    );
  }, [committedUpper, parseBound, max]);

  const lower = parseBound(minText, min);
  const upper = parseBound(maxText, max);
  // The slider always renders two in-bounds, ascending thumbs.
  const sliderValue: [number, number] = [Math.min(lower, upper), Math.max(lower, upper)];

  // Orders the pair (so an inverted entry can't emit an impossible range) and
  // keeps only a bound that narrows the track; clears the filter at the extremes.
  const commit = useCallback(
    (rawLower: number, rawUpper: number) => {
      const nextLower = Math.min(rawLower, rawUpper);
      const nextUpper = Math.max(rawLower, rawUpper);
      const $gte = nextLower > min ? nextLower : undefined;
      const $lte = nextUpper < max ? nextUpper : undefined;
      column.setFilterValue($gte === undefined && $lte === undefined ? undefined : { $gte, $lte });
    },
    [column, min, max]
  );

  const handleSliderChange = ([nextLower, nextUpper]: [number, number]) => {
    setMinText(String(nextLower));
    setMaxText(String(nextUpper));
  };

  // The text inputs update live so the slider can preview the range, but the
  // filter is committed on blur / Enter. Committing per keystroke while ordering
  // would let the resync swap the two fields out from under the user mid-edit.
  const applyTextEdit = () => {
    const nextLower = Math.min(lower, upper);
    const nextUpper = Math.max(lower, upper);
    setMinText(String(nextLower));
    setMaxText(String(nextUpper));
    commit(nextLower, nextUpper);
  };

  const handleTextKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') applyTextEdit();
  };

  return (
    <Stack gap="density-lg" data-testid={`column-filter-${column.id}`}>
      <RangeSlider
        aria-label={`${label} range`}
        min={min}
        max={max}
        step={step}
        value={sliderValue}
        onValueChange={handleSliderChange}
        onValueCommit={([nextLower, nextUpper]) => commit(nextLower, nextUpper)}
      />
      <Flex gap="2">
        <TextInput
          type="number"
          aria-label={`${label} minimum`}
          placeholder="Min"
          value={minText}
          onValueChange={(text) => setMinText(text)}
          attributes={{
            Input: {
              min,
              max,
              step,
              inputMode: 'numeric',
              onBlur: applyTextEdit,
              onKeyDown: handleTextKeyDown,
            },
          }}
        />
        <TextInput
          type="number"
          aria-label={`${label} maximum`}
          placeholder="Max"
          value={maxText}
          onValueChange={(text) => setMaxText(text)}
          attributes={{
            Input: {
              min,
              max,
              step,
              inputMode: 'numeric',
              onBlur: applyTextEdit,
              onKeyDown: handleTextKeyDown,
            },
          }}
        />
      </Flex>
    </Stack>
  );
}
