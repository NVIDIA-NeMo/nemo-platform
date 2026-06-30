// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { act, renderHook, waitFor } from '@testing-library/react';

import { useInferredDatasetSchema } from './index';

vi.mock('hyparquet', () => ({
  parquetRead: vi.fn(
    async (options: {
      rowStart?: number;
      rowEnd?: number;
      onComplete?: (rows: Record<string, unknown>[]) => void;
    }) => {
      const allRows: Record<string, unknown>[] = [
        { id: 1n, label: 'alice' },
        { id: 2n, label: 'bob' },
      ];
      const start = options.rowStart ?? 0;
      const end = options.rowEnd ?? allRows.length;
      options.onComplete?.(allRows.slice(start, end));
    }
  ),
}));

function makeJsonlFile(name: string, rows: Array<Record<string, unknown>>): File {
  const text = rows.map((r) => JSON.stringify(r)).join('\n');
  return new File([text], name, { type: 'application/x-ndjson' });
}

function makeJsonFile(name: string, value: unknown): File {
  return new File([JSON.stringify(value)], name, { type: 'application/json' });
}

describe('useInferredDatasetSchema', () => {
  it('returns empty state when there are no supported files and no existing metadata', () => {
    const { result } = renderHook(() => useInferredDatasetSchema([]));
    expect(result.current.metadata).toBeNull();
    expect(result.current.text).toBe('');
    expect(result.current.validation).toEqual({ valid: true, errors: [] });
    expect(result.current.isInferring).toBe(false);
  });

  it('infers a JSON Schema from the 0th row of a JSONL file', async () => {
    const file = makeJsonlFile('data.jsonl', [
      { id: 1, name: 'a' },
      { id: 2, name: 'b' },
    ]);
    const { result } = renderHook(() => useInferredDatasetSchema([file]));

    await waitFor(() => expect(result.current.isInferring).toBe(false));
    expect(result.current.metadata).not.toBeNull();
    const meta = result.current.metadata!;
    // Single new file collapses to inline schema.
    expect(meta.schema).toMatchObject({
      type: 'object',
      properties: {
        id: { type: 'integer' },
        name: { type: 'string' },
      },
    });
    expect(meta.schema_defs).toEqual({});
    expect(meta.schemas_by_path).toEqual({});
    // Editor text is the serialized payload.
    expect(JSON.parse(result.current.text)).toEqual(meta);
  });

  it('dedupes per-file schemas across mixed JSON + JSONL files', async () => {
    const a = makeJsonlFile('a.jsonl', [{ x: 1 }]);
    const b = makeJsonFile('b.json', { y: 'hi' });
    const { result } = renderHook(() => useInferredDatasetSchema([a, b]));

    await waitFor(() => expect(result.current.isInferring).toBe(false));
    const meta = result.current.metadata!;
    // Two different shapes -> schema_defs + schemas_by_path divergent entries.
    expect(Object.keys(meta.schema_defs ?? {}).length).toBe(2);
    expect(typeof meta.schema).toBe('string');
  });

  it('skips files with unsupported extensions', async () => {
    const supported = makeJsonlFile('data.jsonl', [{ a: 1 }]);
    const unknown = new File(['data'], 'data.feather', { type: 'application/octet-stream' });
    const { result } = renderHook(() => useInferredDatasetSchema([supported, unknown]));

    await waitFor(() => expect(result.current.isInferring).toBe(false));
    const meta = result.current.metadata!;
    // Only the .jsonl was inferred -> single inline schema.
    expect(meta.schema_defs).toEqual({});
    expect(meta.schemas_by_path).toEqual({});
  });

  it('infers a JSON Schema from the first row of a CSV file', async () => {
    const csvContent = 'name,score,active\nalice,42,true\nbob,7,false\n';
    const file = new File([csvContent], 'data.csv', { type: 'text/csv' });
    const { result } = renderHook(() => useInferredDatasetSchema([file]));

    await waitFor(() => expect(result.current.isInferring).toBe(false));
    expect(result.current.metadata).not.toBeNull();
    const meta = result.current.metadata!;
    // CSV columns all parse as strings via papaparse header mode.
    expect(meta.schema).toMatchObject({
      type: 'object',
      properties: {
        name: { type: 'string' },
        score: { type: 'string' },
        active: { type: 'string' },
      },
    });
    expect(meta.schema_defs).toEqual({});
    expect(meta.schemas_by_path).toEqual({});
  });

  it('honors the user edit until reset() is called', async () => {
    const file = makeJsonlFile('data.jsonl', [{ id: 1 }]);
    const { result } = renderHook(() => useInferredDatasetSchema([file]));

    await waitFor(() => expect(result.current.isInferring).toBe(false));
    const inferredText = result.current.text;

    act(() => result.current.setText('{ "type": "string" }'));
    expect(result.current.text).toBe('{ "type": "string" }');

    act(() => result.current.reset());
    await waitFor(() => expect(result.current.text).toBe(inferredText));
  });

  it('reports validation errors when the user-edited text is invalid JSON', async () => {
    const file = makeJsonlFile('data.jsonl', [{ id: 1 }]);
    const { result } = renderHook(() => useInferredDatasetSchema([file]));

    await waitFor(() => expect(result.current.isInferring).toBe(false));

    act(() => result.current.setText('{ not json }'));
    expect(result.current.validation.valid).toBe(false);
    expect(result.current.validation.errors[0]).toMatch(/Invalid JSON/);
  });

  it('reports validation errors when the user-edited text is not a valid JSON Schema', async () => {
    const file = makeJsonlFile('data.jsonl', [{ id: 1 }]);
    const { result } = renderHook(() => useInferredDatasetSchema([file]));

    await waitFor(() => expect(result.current.isInferring).toBe(false));

    act(() => result.current.setText('{ "type": "foobar" }'));
    expect(result.current.validation.valid).toBe(false);
  });

  it('infers a JSON Schema from the first row of a Parquet file', async () => {
    // The hyparquet mock (top of file) returns [{ id: 1n, label: 'alice' }, ...].
    // BigInt values are coerced to number before inferJsonSchema sees them.
    const file = new File([], 'data.parquet', { type: 'application/octet-stream' });
    const { result } = renderHook(() => useInferredDatasetSchema([file]));

    await waitFor(() => expect(result.current.isInferring).toBe(false));
    expect(result.current.metadata).not.toBeNull();
    const meta = result.current.metadata!;
    expect(meta.schema).toMatchObject({
      type: 'object',
      properties: {
        id: { type: 'integer' },
        label: { type: 'string' },
      },
    });
    expect(meta.schema_defs).toEqual({});
    expect(meta.schemas_by_path).toEqual({});
  });

  it('merges new files with existing metadata, preserving the existing default', async () => {
    const existing = {
      schema: { type: 'object', properties: { id: { type: 'integer' } } } as Record<
        string,
        unknown
      >,
    };
    const newFile = makeJsonlFile('new.jsonl', [{ different: 'shape' }]);
    const { result } = renderHook(() => useInferredDatasetSchema([newFile], existing));

    await waitFor(() => expect(result.current.isInferring).toBe(false));
    const meta = result.current.metadata!;
    // Existing inline schema is promoted to a def; new divergent file gets its own.
    const defValues = Object.values(meta.schema_defs ?? {});
    expect(defValues.some((d) => JSON.stringify(d).includes('"id"'))).toBe(true);
    expect(defValues.some((d) => JSON.stringify(d).includes('"different"'))).toBe(true);
    expect(meta.schemas_by_path).toHaveProperty('new.jsonl');
  });
});
