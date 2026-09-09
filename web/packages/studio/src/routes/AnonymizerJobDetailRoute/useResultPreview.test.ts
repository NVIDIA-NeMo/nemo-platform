// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useResultPreview } from '@studio/routes/AnonymizerJobDetailRoute/useResultPreview';
import { renderHook } from '@testing-library/react';

const fileContentByPath: Record<string, string> = {
  'metadata.json': JSON.stringify({ original_text_column: 'text' }),
  'dataset.parquet': [
    JSON.stringify({
      text: 'Cheryl Gray lives in Illinois.',
      text_replaced: 'Sofia Nguyen lives in Colorado.',
    }),
  ].join('\n'),
  'trace.parquet': [
    JSON.stringify({
      _detected_entities: {
        entities: [{ value: 'Cheryl Gray', label: 'PERSON', start_position: 0, end_position: 11 }],
      },
      final_entities: {
        entities: [{ value: 'Cheryl Gray', label: 'PERSON', start_position: 0, end_position: 11 }],
      },
      _replacement_map: {
        replacements: [{ original: 'Cheryl Gray', label: 'PERSON', synthetic: 'Sofia Nguyen' }],
      },
    }),
  ].join('\n'),
};

vi.mock('@studio/api/datasets/useDatasetFileContent', () => ({
  useDatasetFileContent: ({ path }: { path: string }) => {
    const key = Object.keys(fileContentByPath).find((suffix) => path.endsWith(suffix));
    return { data: key ? fileContentByPath[key] : undefined, isLoading: false, error: null };
  },
}));

describe('useResultPreview', () => {
  it('merges trace-only entity and replacement-map columns onto dataset rows', () => {
    const { result } = renderHook(() =>
      useResultPreview('workspace', 'fileset/job#results/attempt-1/artifacts')
    );

    expect(result.current.rows).toHaveLength(1);
    expect(result.current.rows[0]._replacement_map).toEqual({
      replacements: [{ original: 'Cheryl Gray', label: 'PERSON', synthetic: 'Sofia Nguyen' }],
    });
    expect(result.current.rows[0].final_entities).toBeDefined();
  });

  it('keeps the dataset row fields alongside the merged trace fields', () => {
    const { result } = renderHook(() =>
      useResultPreview('workspace', 'fileset/job#results/attempt-1/artifacts')
    );

    expect(result.current.rows[0].text).toBe('Cheryl Gray lives in Illinois.');
    expect(result.current.rows[0].text_replaced).toBe('Sofia Nguyen lives in Colorado.');
  });
});
