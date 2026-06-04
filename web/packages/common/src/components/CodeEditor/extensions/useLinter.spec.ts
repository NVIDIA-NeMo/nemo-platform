// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ContentType } from '@nemo/common/src/components/CodeEditor/constants';
import { getLinterExtension } from '@nemo/common/src/components/CodeEditor/extensions/useLinter';
import { jsonlLinter, jsonLinter } from '@nemo/common/src/components/CodeEditor/linters/JsonLinter';
import { yamlLinter } from '@nemo/common/src/components/CodeEditor/linters/yaml';

describe('getLinterExtension', () => {
  it('returns the JSON linter for ContentType.JSON', () => {
    expect(getLinterExtension(ContentType.JSON, false)).toBe(jsonLinter);
  });

  it('returns the JSONL linter for ContentType.JSONL', () => {
    expect(getLinterExtension(ContentType.JSONL, false)).toBe(jsonlLinter);
  });

  it('returns the YAML linter for ContentType.YAML', () => {
    expect(getLinterExtension(ContentType.YAML, false)).toBe(yamlLinter);
  });

  it('returns no linter for ContentType.TEXT (prevents spurious JSON diagnostics on .txt/.log files)', () => {
    expect(getLinterExtension(ContentType.TEXT, false)).toEqual([]);
  });

  it('returns no linter for ContentType.JAVASCRIPT', () => {
    expect(getLinterExtension(ContentType.JAVASCRIPT, false)).toEqual([]);
  });

  it('returns no linter when hideLinter is true, regardless of contentType', () => {
    expect(getLinterExtension(ContentType.JSON, true)).toEqual([]);
    expect(getLinterExtension(ContentType.JSONL, true)).toEqual([]);
    expect(getLinterExtension(ContentType.YAML, true)).toEqual([]);
  });
});
