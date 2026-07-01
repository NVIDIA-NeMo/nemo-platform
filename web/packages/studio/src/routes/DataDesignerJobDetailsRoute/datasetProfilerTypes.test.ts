// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  describeColumnStats,
  formatPercent,
  formatStatCount,
  formatStatDecimal,
  getCategoricalHistogram,
  getColumnTypeLabel,
  getNumericalDistribution,
  getPercentComplete,
  getPercentNull,
  getPercentUnique,
  MISSING_VALUE,
  type ColumnStatistics,
  type DatasetProfilerResults,
} from '@studio/routes/DataDesignerJobDetailsRoute/datasetProfilerTypes';

const baseStats = {
  column_name: 'col',
  num_records: 100,
  num_null: 5,
  num_unique: 80,
  pyarrow_dtype: 'string',
  simple_dtype: 'str',
};

describe('formatStatCount', () => {
  it('formats numbers with locale separators', () => {
    expect(formatStatCount(1234)).toBe((1234).toLocaleString());
  });

  it('renders the calculation-failed sentinel as an em dash', () => {
    expect(formatStatCount(MISSING_VALUE.CALCULATION_FAILED)).toBe('—');
  });

  it('renders the output-format-error sentinel as text', () => {
    expect(formatStatCount(MISSING_VALUE.OUTPUT_FORMAT_ERROR)).toBe('format error');
  });

  it('renders nullish values as an em dash', () => {
    expect(formatStatCount(undefined)).toBe('—');
    expect(formatStatCount(null)).toBe('—');
  });
});

describe('formatStatDecimal', () => {
  it('limits to one fractional digit', () => {
    expect(formatStatDecimal(12.345)).toBe((12.3).toLocaleString());
  });

  it('passes sentinels through', () => {
    expect(formatStatDecimal(MISSING_VALUE.CALCULATION_FAILED)).toBe('—');
  });
});

describe('formatPercent', () => {
  it('formats a percentage to one decimal', () => {
    expect(formatPercent(42.5)).toBe('42.5%');
  });

  it('renders undefined as an em dash', () => {
    expect(formatPercent(undefined)).toBe('—');
  });
});

describe('getPercentComplete', () => {
  it('computes completion percentage', () => {
    const results = { num_records: 50, target_num_records: 200 } as DatasetProfilerResults;
    expect(getPercentComplete(results)).toBe(25);
  });

  it('returns 0 when the target is non-positive', () => {
    const results = { num_records: 10, target_num_records: 0 } as DatasetProfilerResults;
    expect(getPercentComplete(results)).toBe(0);
  });
});

describe('getPercentNull / getPercentUnique', () => {
  it('computes percentages from counts', () => {
    const stats = { ...baseStats, column_type: 'general' } as ColumnStatistics;
    expect(getPercentNull(stats)).toBe(5);
    expect(getPercentUnique(stats)).toBe(80);
  });

  it('returns undefined when a count is a missing-value sentinel', () => {
    const stats = {
      ...baseStats,
      num_null: MISSING_VALUE.CALCULATION_FAILED,
      num_unique: MISSING_VALUE.CALCULATION_FAILED,
      column_type: 'general',
    } as ColumnStatistics;
    expect(getPercentNull(stats)).toBeUndefined();
    expect(getPercentUnique(stats)).toBeUndefined();
  });
});

describe('getColumnTypeLabel', () => {
  it('returns the column type for non-sampler columns', () => {
    const stats = { ...baseStats, column_type: 'llm-text' } as ColumnStatistics;
    expect(getColumnTypeLabel(stats)).toBe('llm-text');
  });

  it('includes the sampler subtype for sampler columns', () => {
    const stats = {
      ...baseStats,
      column_type: 'sampler',
      sampler_type: 'category',
      distribution_type: 'categorical',
      distribution: null,
    } as ColumnStatistics;
    expect(getColumnTypeLabel(stats)).toBe('sampler · category');
  });
});

describe('describeColumnStats (variant → render mapping)', () => {
  it('summarizes LLM columns with token usage', () => {
    const stats = {
      ...baseStats,
      column_type: 'llm-text',
      input_tokens_mean: 120.4,
      input_tokens_median: 100,
      input_tokens_stddev: 10,
      output_tokens_mean: 45.9,
      output_tokens_median: 40,
      output_tokens_stddev: 5,
    } as ColumnStatistics;
    expect(describeColumnStats(stats)).toBe(
      `Tokens in/out (avg): ${formatStatDecimal(120.4)} / ${formatStatDecimal(45.9)}`
    );
  });

  it('summarizes validation columns with valid-record counts', () => {
    const stats = {
      ...baseStats,
      column_type: 'validation',
      num_valid_records: 95,
    } as ColumnStatistics;
    expect(describeColumnStats(stats)).toBe('Valid records: 95');
  });

  it('summarizes categorical sampler columns with the most common value', () => {
    const stats = {
      ...baseStats,
      column_type: 'sampler',
      sampler_type: 'category',
      distribution_type: 'categorical',
      distribution: {
        most_common_value: 'positive',
        least_common_value: 'negative',
        histogram: { categories: ['positive', 'negative'], counts: [70, 30] },
      },
    } as ColumnStatistics;
    expect(describeColumnStats(stats)).toBe('Most common: positive');
  });

  it('summarizes numerical sampler columns with min/max/mean', () => {
    const stats = {
      ...baseStats,
      column_type: 'sampler',
      sampler_type: 'gaussian',
      distribution_type: 'numerical',
      distribution: { min: 1, max: 5, mean: 3.2, stddev: 1.1, median: 3 },
    } as ColumnStatistics;
    expect(describeColumnStats(stats)).toBe(
      `min ${formatStatDecimal(1)} · max ${formatStatDecimal(5)} · mean ${formatStatDecimal(3.2)}`
    );
  });

  it('falls back to an em dash for plain and unknown column types', () => {
    expect(describeColumnStats({ ...baseStats, column_type: 'general' } as ColumnStatistics)).toBe(
      '—'
    );
    expect(
      describeColumnStats({ ...baseStats, column_type: 'some-plugin-type' } as ColumnStatistics)
    ).toBe('—');
  });

  it('handles a missing sampler distribution without throwing', () => {
    const stats = {
      ...baseStats,
      column_type: 'sampler',
      sampler_type: 'uuid',
      distribution_type: 'other',
      distribution: null,
    } as ColumnStatistics;
    expect(describeColumnStats(stats)).toBe('—');
  });
});

describe('getCategoricalHistogram', () => {
  const histogram = { categories: ['positive', 'negative'], counts: [70, 30] };

  it('returns the histogram for a categorical sampler column', () => {
    const stats = {
      ...baseStats,
      column_type: 'sampler',
      sampler_type: 'category',
      distribution_type: 'categorical',
      distribution: {
        most_common_value: 'positive',
        least_common_value: 'negative',
        histogram,
      },
    } as ColumnStatistics;
    expect(getCategoricalHistogram(stats)).toEqual(histogram);
  });

  it('returns null for numerical sampler columns', () => {
    const stats = {
      ...baseStats,
      column_type: 'sampler',
      sampler_type: 'gaussian',
      distribution_type: 'numerical',
      distribution: { min: 1, max: 5, mean: 3, stddev: 1, median: 3 },
    } as ColumnStatistics;
    expect(getCategoricalHistogram(stats)).toBeNull();
  });

  it('returns null for non-sampler columns and missing distributions', () => {
    expect(
      getCategoricalHistogram({ ...baseStats, column_type: 'llm-text' } as ColumnStatistics)
    ).toBeNull();
    expect(
      getCategoricalHistogram({
        ...baseStats,
        column_type: 'sampler',
        sampler_type: 'uuid',
        distribution_type: 'other',
        distribution: null,
      } as ColumnStatistics)
    ).toBeNull();
    expect(
      getCategoricalHistogram({
        ...baseStats,
        column_type: 'sampler',
        sampler_type: 'category',
        distribution_type: 'categorical',
        distribution: MISSING_VALUE.CALCULATION_FAILED,
      } as ColumnStatistics)
    ).toBeNull();
  });
});

describe('getNumericalDistribution', () => {
  it('returns the distribution for a numerical sampler column', () => {
    const distribution = { min: 1, max: 5, mean: 3.2, stddev: 1.1, median: 3 };
    const stats = {
      ...baseStats,
      column_type: 'sampler',
      sampler_type: 'gaussian',
      distribution_type: 'numerical',
      distribution,
    } as ColumnStatistics;
    expect(getNumericalDistribution(stats)).toEqual(distribution);
  });

  it('returns null for categorical and non-sampler columns', () => {
    const categorical = {
      ...baseStats,
      column_type: 'sampler',
      sampler_type: 'category',
      distribution_type: 'categorical',
      distribution: {
        most_common_value: 'a',
        least_common_value: 'b',
        histogram: { categories: ['a', 'b'], counts: [1, 2] },
      },
    } as ColumnStatistics;
    expect(getNumericalDistribution(categorical)).toBeNull();
    expect(
      getNumericalDistribution({ ...baseStats, column_type: 'general' } as ColumnStatistics)
    ).toBeNull();
  });
});
