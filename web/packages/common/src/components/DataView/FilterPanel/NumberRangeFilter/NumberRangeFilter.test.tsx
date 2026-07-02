// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { NumberRangeFilterControl } from '@nemo/common/src/components/DataView/FilterPanel/NumberRangeFilter';
import {
  formatNumberRange,
  isNumberRangeFilter,
  numberRangeFilter,
  type NumberRangeFilterConfig,
  type NumberRangeFilterValue,
} from '@nemo/common/src/components/DataView/FilterPanel/NumberRangeFilter/util';
import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';

/**
 * Renders the control in a stateful harness (like a real DataView column) and spies
 * on emitted values. Defaults to a bounded 0–100 track; omit min/max for unbounded.
 */
function renderControl(
  initial?: NumberRangeFilterValue,
  config: NumberRangeFilterConfig = { min: 0, max: 100, step: 1 }
) {
  const setFilterValue = vi.fn();

  function Harness() {
    const [value, setValue] = useState<NumberRangeFilterValue | undefined>(initial);
    const column = {
      id: 'score',
      getFilterValue: () => value,
      setFilterValue: (next: unknown) => {
        setFilterValue(next);
        setValue(next as NumberRangeFilterValue | undefined);
      },
      columnDef: {
        header: 'Score',
        meta: { filter: numberRangeFilter('Score', config) },
      },
    };
    return <NumberRangeFilterControl column={column as never} />;
  }

  render(<Harness />);
  return { setFilterValue };
}

describe('numberRangeFilter', () => {
  it('builds a custom filter def with the numberRange variant; bounds are optional', () => {
    const def = numberRangeFilter('Score');
    expect(def).toMatchObject({
      label: 'Score',
      type: 'custom',
      filterVariant: 'numberRange',
      step: 1,
    });
    // Bounds default to undefined (unbounded / slider-less) unless supplied.
    expect(def.min).toBeUndefined();
    expect(def.max).toBeUndefined();
    expect(numberRangeFilter('Price', { min: 10, max: 500, step: 25 })).toMatchObject({
      min: 10,
      max: 500,
      step: 25,
    });
  });

  it('narrows only numberRange filters via the type guard', () => {
    const dateLikeFilter = { type: 'custom', filterVariant: 'datetime' };
    expect(isNumberRangeFilter(numberRangeFilter('Score'))).toBe(true);
    expect(isNumberRangeFilter({ type: 'text' })).toBe(false);
    expect(isNumberRangeFilter(dateLikeFilter)).toBe(false);
    expect(isNumberRangeFilter(undefined)).toBe(false);
  });

  it('formats ranges, including open-ended ones', () => {
    expect(formatNumberRange(10, 50)).toBe('10 – 50');
    expect(formatNumberRange(10, undefined)).toBe('≥ 10');
    expect(formatNumberRange(undefined, 50)).toBe('≤ 50');
    expect(formatNumberRange(undefined, undefined)).toBe('');
  });
});

describe('NumberRangeFilterControl', () => {
  it('renders a two-thumb slider and min/max inputs', () => {
    renderControl();

    expect(screen.getAllByRole('slider')).toHaveLength(2);
    expect(screen.getByPlaceholderText('Min')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Max')).toBeInTheDocument();
  });

  it('emits a $gte bound when the minimum is narrowed (on blur)', () => {
    const { setFilterValue } = renderControl();

    const min = screen.getByPlaceholderText('Min');
    fireEvent.change(min, { target: { value: '20' } });
    fireEvent.blur(min);

    expect(setFilterValue).toHaveBeenLastCalledWith({ $gte: 20, $lte: undefined });
  });

  it('emits a $lte bound when the maximum is narrowed (on blur)', () => {
    const { setFilterValue } = renderControl();

    const max = screen.getByPlaceholderText('Max');
    fireEvent.change(max, { target: { value: '80' } });
    fireEvent.blur(max);

    expect(setFilterValue).toHaveBeenLastCalledWith({ $gte: undefined, $lte: 80 });
  });

  it('commits on Enter as well as blur', () => {
    const { setFilterValue } = renderControl();

    const min = screen.getByPlaceholderText('Min');
    fireEvent.change(min, { target: { value: '20' } });
    fireEvent.keyDown(min, { key: 'Enter' });

    expect(setFilterValue).toHaveBeenLastCalledWith({ $gte: 20, $lte: undefined });
  });

  it('clears the filter when both bounds return to the track extremes', () => {
    const { setFilterValue } = renderControl({ $gte: 20 });

    // The min input starts at 20; typing the track minimum opens the lower bound.
    const min = screen.getByPlaceholderText('Min');
    fireEvent.change(min, { target: { value: '0' } });
    fireEvent.blur(min);

    expect(setFilterValue).toHaveBeenLastCalledWith(undefined);
  });

  it('clamps out-of-range input to the configured bounds', () => {
    const { setFilterValue } = renderControl();

    const max = screen.getByPlaceholderText('Max');
    fireEvent.change(max, { target: { value: '999' } });
    fireEvent.blur(max);

    // 999 is clamped to the track maximum (100), which no longer narrows the range.
    expect(setFilterValue).toHaveBeenLastCalledWith(undefined);
  });

  it('orders an inverted entry instead of emitting an impossible range', () => {
    const { setFilterValue } = renderControl();

    const min = screen.getByPlaceholderText('Min');
    const max = screen.getByPlaceholderText('Max');
    fireEvent.change(min, { target: { value: '80' } });
    fireEvent.change(max, { target: { value: '30' } });
    fireEvent.blur(max);

    // The bounds are ordered, never emitted as { $gte: 80, $lte: 30 }.
    expect(setFilterValue).toHaveBeenLastCalledWith({ $gte: 30, $lte: 80 });
    // ...and the inputs settle to the ordered values, matching the slider.
    expect(min).toHaveValue(30);
    expect(max).toHaveValue(80);
  });
});

describe('NumberRangeFilterControl (unbounded)', () => {
  // A config without min/max renders the slider-less variant with empty inputs.
  const UNBOUNDED: NumberRangeFilterConfig = { step: 1 };

  it('hides the slider and starts the inputs empty so placeholders show', () => {
    renderControl(undefined, UNBOUNDED);

    expect(screen.queryByRole('slider')).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText('Min')).toHaveValue(null);
    expect(screen.getByPlaceholderText('Max')).toHaveValue(null);
  });

  it('emits the typed lower bound verbatim (no track to narrow against)', () => {
    const { setFilterValue } = renderControl(undefined, UNBOUNDED);

    const min = screen.getByPlaceholderText('Min');
    fireEvent.change(min, { target: { value: '5' } });
    fireEvent.blur(min);

    expect(setFilterValue).toHaveBeenLastCalledWith({ $gte: 5, $lte: undefined });
  });

  it('emits the typed upper bound verbatim', () => {
    const { setFilterValue } = renderControl(undefined, UNBOUNDED);

    const max = screen.getByPlaceholderText('Max');
    fireEvent.change(max, { target: { value: '250' } });
    fireEvent.blur(max);

    expect(setFilterValue).toHaveBeenLastCalledWith({ $gte: undefined, $lte: 250 });
  });

  it('opens an end of the range when its field is cleared', () => {
    const { setFilterValue } = renderControl({ $gte: 5, $lte: 250 }, UNBOUNDED);

    const min = screen.getByPlaceholderText('Min');
    fireEvent.change(min, { target: { value: '' } });
    fireEvent.blur(min);

    expect(setFilterValue).toHaveBeenLastCalledWith({ $gte: undefined, $lte: 250 });
  });
});
