// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  isNumberRangeFilter,
  type NumberRangeFilterValue,
} from '@nemo/common/src/components/DataView/FilterPanel/NumberRangeFilter/util';
import type { DataViewColumn } from '@nemo/common/src/components/DataView/FilterPanel/types';
import { Group, RangeSlider, Stack, TextInput } from '@nvidia/foundations-react-core';
import { useCallback, useEffect, useState, type KeyboardEvent } from 'react';

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

/**
 * Numeric range filter storing `{ $gte, $lte }`. With both `min` and `max` it
 * renders a RangeSlider + inputs; with either omitted, just open-ended inputs.
 */
export function NumberRangeFilterControl({ column }: { column: DataViewColumn }) {
  const filterDef = column.columnDef.meta?.filter;
  const rangeDef = isNumberRangeFilter(filterDef) ? filterDef : undefined;
  const min = rangeDef?.min;
  const max = rangeDef?.max;
  const step = rangeDef?.step ?? 1;
  // The slider only renders when it has a full track to draw; without both
  // bounds the control is a pair of open-ended inputs.
  const hasBounds = min != null && max != null;
  const header = column.columnDef.header;
  const label = filterDef?.label ?? (typeof header === 'string' ? header : column.id);

  const committed = column.getFilterValue() as NumberRangeFilterValue | undefined;
  // In bounded mode an empty field represents the bound; in unbounded mode it
  // represents an open end, so the field stays empty and its placeholder shows.
  const committedLower = committed?.$gte ?? (hasBounds ? min : undefined);
  const committedUpper = committed?.$lte ?? (hasBounds ? max : undefined);

  // Local string state lets users edit each field freely — including clearing it
  // or typing partial values like "1." — without snapping back on every keystroke.
  const [minText, setMinText] = useState(committedLower != null ? String(committedLower) : '');
  const [maxText, setMaxText] = useState(committedUpper != null ? String(committedUpper) : '');

  // Parses a field into a number, or `undefined` when empty / non-numeric.
  // Bounded input is clamped to the track; unbounded input is taken verbatim.
  const parseField = useCallback(
    (text: string): number | undefined => {
      const trimmed = text.trim();
      if (trimmed === '') return undefined;
      const parsed = Number(trimmed);
      if (!Number.isFinite(parsed)) return undefined;
      return hasBounds ? clamp(parsed, min, max) : parsed;
    },
    [hasBounds, min, max]
  );

  // Resync inputs when the committed value changes externally (chip removed, reset,
  // slider release). Skip when the field already parses to it, so typing isn't clobbered.
  useEffect(() => {
    setMinText((curr) =>
      parseField(curr) === committedLower
        ? curr
        : committedLower != null
          ? String(committedLower)
          : ''
    );
  }, [committedLower, parseField]);
  useEffect(() => {
    setMaxText((curr) =>
      parseField(curr) === committedUpper
        ? curr
        : committedUpper != null
          ? String(committedUpper)
          : ''
    );
  }, [committedUpper, parseField]);

  // Orders the pair so an inverted entry can't emit an impossible range, and in
  // bounded mode keeps only a bound that narrows the track (clears at the extremes).
  const commit = useCallback(
    (rawLower: number | undefined, rawUpper: number | undefined) => {
      let nextLower = rawLower;
      let nextUpper = rawUpper;
      if (nextLower != null && nextUpper != null && nextLower > nextUpper) {
        [nextLower, nextUpper] = [nextUpper, nextLower];
      }
      const $gte = nextLower != null && (min == null || nextLower > min) ? nextLower : undefined;
      const $lte = nextUpper != null && (max == null || nextUpper < max) ? nextUpper : undefined;
      column.setFilterValue($gte === undefined && $lte === undefined ? undefined : { $gte, $lte });
    },
    [column, min, max]
  );

  const handleSliderChange = ([nextLower, nextUpper]: [number, number]) => {
    setMinText(String(nextLower));
    setMaxText(String(nextUpper));
  };

  // Inputs update live to preview on the slider but commit on blur / Enter:
  // committing per keystroke would let the resync swap fields mid-edit.
  const applyTextEdit = () => {
    let nextLower = parseField(minText);
    let nextUpper = parseField(maxText);
    if (nextLower != null && nextUpper != null && nextLower > nextUpper) {
      [nextLower, nextUpper] = [nextUpper, nextLower];
    }
    // Reflect the ordered/clamped values back into the fields. A bounded field
    // falls back to its bound; an unbounded open end stays empty.
    setMinText(nextLower != null ? String(nextLower) : hasBounds ? String(min) : '');
    setMaxText(nextUpper != null ? String(nextUpper) : hasBounds ? String(max) : '');
    commit(nextLower, nextUpper);
  };

  const handleTextKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') applyTextEdit();
  };

  // The slider always renders two in-bounds, ascending thumbs; an empty field
  // falls back to its bound. Only computed when bounds exist (bounded mode).
  const sliderValue: [number, number] | undefined = hasBounds
    ? [
        Math.min(parseField(minText) ?? min, parseField(maxText) ?? max),
        Math.max(parseField(minText) ?? min, parseField(maxText) ?? max),
      ]
    : undefined;

  return (
    <Stack gap="density-lg" data-testid={`column-filter-${column.id}`}>
      {hasBounds && sliderValue && (
        <RangeSlider
          aria-label={`${label} range`}
          min={min}
          max={max}
          step={step}
          value={sliderValue}
          onValueChange={handleSliderChange}
          onValueCommit={([nextLower, nextUpper]) => commit(nextLower, nextUpper)}
        />
      )}
      <Group className="w-full [&>*]:!h-[var(--nv-input-height)]">
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
      </Group>
    </Stack>
  );
}
