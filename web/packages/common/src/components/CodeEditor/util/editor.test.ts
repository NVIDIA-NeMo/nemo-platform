// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { findNodeRanges } from '@nemo/common/src/components/CodeEditor/util/editor';

describe('findNodeRanges', () => {
  it('should find a single JSON object', () => {
    const doc = '{"name": "John", "age": 30}';
    const ranges = findNodeRanges(doc);

    expect(ranges).toHaveLength(1);
    expect(ranges[0]).toEqual({ start: 0, end: 27 });
  });

  it('should find multiple JSON objects in a string', () => {
    const doc = '{"name": "John"} {"name": "Jane"}';
    const ranges = findNodeRanges(doc);

    expect(ranges).toHaveLength(2);
    expect(ranges[0]).toEqual({ start: 0, end: 16 });
    expect(ranges[1]).toEqual({ start: 17, end: 33 });
  });

  it('should handle nested JSON objects', () => {
    const doc = '{"name": "John", "address": {"city": "New York"}}';
    const ranges = findNodeRanges(doc);

    expect(ranges).toHaveLength(1);
    expect(ranges[0]).toEqual({ start: 0, end: 49 });
  });

  it('should handle JSONL format (one object per line)', () => {
    const doc = '{"name": "John"}\n{"name": "Jane"}\n{"name": "Bob"}';
    const ranges = findNodeRanges(doc);

    expect(ranges).toHaveLength(3);
    expect(ranges[0]).toEqual({ start: 0, end: 16 });
    expect(ranges[1]).toEqual({ start: 17, end: 33 });
    expect(ranges[2]).toEqual({ start: 34, end: 49 });
  });

  it('should handle empty JSON objects', () => {
    const doc = '{}';
    const ranges = findNodeRanges(doc);

    expect(ranges).toHaveLength(1);
    expect(ranges[0]).toEqual({ start: 0, end: 2 });
  });

  it('should handle JSON objects with escaped braces', () => {
    const doc = '{"text": "This is a {braced} text"}';
    const ranges = findNodeRanges(doc);

    expect(ranges).toHaveLength(1);
    expect(ranges[0]).toEqual({ start: 0, end: 35 });
  });

  it('should return empty array for invalid JSON', () => {
    const doc = '{"name": "John"'; // Missing closing brace
    const ranges = findNodeRanges(doc);

    expect(ranges).toHaveLength(0);
  });

  it('should handle multiple nested objects', () => {
    const doc = '{"a": {"b": {"c": 1}}}';
    const ranges = findNodeRanges(doc);

    expect(ranges).toHaveLength(1);
    expect(ranges[0]).toEqual({ start: 0, end: 22 });
  });

  it('should handle JSON objects with arrays', () => {
    const doc = '{"items": [1, 2, 3]}';
    const ranges = findNodeRanges(doc);

    expect(ranges).toHaveLength(1);
    expect(ranges[0]).toEqual({ start: 0, end: 20 });
  });
});
