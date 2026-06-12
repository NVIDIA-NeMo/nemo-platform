// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { DatasetMetadataContent } from '@nemo/sdk/generated/platform/schema';
import { getSchemaCellLabel } from '@studio/routes/FilesetDetailRoute/FilesTab/schemaColumn';

const inlineSchema = { type: 'object', properties: { id: { type: 'string' } } };

describe('getSchemaCellLabel', () => {
  it('returns null for non-data file paths', () => {
    const meta: DatasetMetadataContent = {
      schema: 'schema_1',
      schema_defs: { schema_1: inlineSchema },
    };
    expect(getSchemaCellLabel('README.md', meta)).toBe(null);
    expect(getSchemaCellLabel('assets/logo.png', meta)).toBe(null);
    expect(getSchemaCellLabel('data/model.safetensors', meta)).toBe(null);
  });

  it('returns the schema key when schemas_by_path maps the file to a string ref', () => {
    const meta: DatasetMetadataContent = {
      schema_defs: { schema_1: inlineSchema, schema_2: inlineSchema },
      schemas_by_path: { 'data/a.jsonl': 'schema_2' },
    };
    expect(getSchemaCellLabel('data/a.jsonl', meta)).toBe('schema_2');
  });

  it('returns null when schemas_by_path maps the file to an inline object (hand-edited edge case)', () => {
    const meta: DatasetMetadataContent = {
      schemas_by_path: { 'data/b.jsonl': inlineSchema },
    };
    expect(getSchemaCellLabel('data/b.jsonl', meta)).toBe(null);
  });

  it('falls back to the root schema key when root is a string ref and no per-file mapping', () => {
    const meta: DatasetMetadataContent = {
      schema: 'schema_1',
      schema_defs: { schema_1: inlineSchema },
    };
    expect(getSchemaCellLabel('train.jsonl', meta)).toBe('schema_1');
  });

  it('returns "default" when root schema is inline and no per-file mapping', () => {
    const meta: DatasetMetadataContent = {
      schema: inlineSchema,
    };
    expect(getSchemaCellLabel('train.jsonl', meta)).toBe('default');
  });

  it('returns null when no per-file mapping and no root schema', () => {
    const meta: DatasetMetadataContent = {
      schema_defs: { schema_1: inlineSchema },
    };
    expect(getSchemaCellLabel('train.jsonl', meta)).toBe(null);
  });

  it('returns null when metadata is undefined', () => {
    expect(getSchemaCellLabel('train.jsonl', undefined)).toBe(null);
  });

  it('returns null when root schema is null (backend cleared-schema state)', () => {
    // Backend Pydantic type is `dict | str | None` — null means "cleared",
    // which serializes to JSON null. Distinct from the field being absent.
    const meta = { schema: null } as unknown as DatasetMetadataContent;
    expect(getSchemaCellLabel('train.jsonl', meta)).toBe(null);
  });

  it('matches case-insensitive json/jsonl extensions', () => {
    const meta: DatasetMetadataContent = { schema: inlineSchema };
    expect(getSchemaCellLabel('TRAIN.JSONL', meta)).toBe('default');
    expect(getSchemaCellLabel('data.Json', meta)).toBe('default');
  });
});
