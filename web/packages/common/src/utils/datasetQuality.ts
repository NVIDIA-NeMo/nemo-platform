// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { findMessagesArray } from '@nemo/common/src/utils/file';

export type DatasetQualityCode =
  | 'EMPTY_FILE'
  | 'INVALID_ENCODING'
  | 'INVALID_JSON_LINES'
  | 'UNKNOWN_SCHEMA'
  | 'NULL_OR_EMPTY_FIELDS'
  | 'LONG_ENTRIES';

export interface DatasetQualityIssue {
  severity: 'error' | 'warning';
  code: DatasetQualityCode;
  message: string;
  /** 1-based line numbers affected (first 10 only) */
  affectedLines?: number[];
  /** Total count of affected lines */
  count?: number;
}

export interface DatasetQualityReport {
  fileName: string;
  hasErrors: boolean;
  hasWarnings: boolean;
  issues: DatasetQualityIssue[];
  /** Number of lines actually scanned (may be less than totalLines for large files) */
  scannedLines: number;
  totalLines: number;
}

const MAX_SCAN_LINES = 1000;

const MAX_AFFECTED_LINE_COUNT = 10;

/** ~8192 tokens at ~4 chars/token */
const LONG_ENTRY_CHAR_THRESHOLD = 32_768;

const PROMPT_KEYS = ['prompt', 'question'];
const COMPLETION_KEYS = ['completion', 'ideal_response', 'response', 'output', 'answer'];

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`;
}

/**
 * Runs dataset quality checks on a JSONL file and returns a structured report.
 * Errors indicate the file should not be uploaded as-is; warnings are advisory.
 *
 * Checks performed:
 * - UTF-16 BOM detection (error)
 * - Empty file (error)
 * - Invalid JSON on any line (error)
 * - Unknown fine-tuning schema — no messages or prompt/completion fields (warning)
 * - Null or empty field values (warning)
 * - Lines exceeding estimated context window (~8192 tokens) (warning)
 *
 * For files with more than 1000 lines, only the first 1000 are scanned.
 */
export async function checkDatasetQuality(file: File): Promise<DatasetQualityReport> {
  const issues: DatasetQualityIssue[] = [];

  // 1. Encoding — detect UTF-16 via BOM before reading as text
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer, 0, Math.min(4, buffer.byteLength));
  const isUtf16Le = bytes[0] === 0xff && bytes[1] === 0xfe;
  const isUtf16Be = bytes[0] === 0xfe && bytes[1] === 0xff;
  if (isUtf16Le || isUtf16Be) {
    issues.push({
      severity: 'error',
      code: 'INVALID_ENCODING',
      message: 'File is UTF-16 encoded. Re-save as UTF-8 before uploading.',
    });
    return {
      fileName: file.name,
      hasErrors: true,
      hasWarnings: false,
      issues,
      scannedLines: 0,
      totalLines: 0,
    };
  }

  // 2. Read text and split into non-empty lines
  const text = await file.text();
  const allLines = text.split('\n').filter((l) => l.trim().length > 0);
  const totalLines = allLines.length;

  if (totalLines === 0) {
    issues.push({
      severity: 'error',
      code: 'EMPTY_FILE',
      message: 'File is empty or contains only whitespace.',
    });
    return {
      fileName: file.name,
      hasErrors: true,
      hasWarnings: false,
      issues,
      scannedLines: 0,
      totalLines: 0,
    };
  }

  const scanLines = allLines.slice(0, MAX_SCAN_LINES);
  const scannedLines = Math.min(MAX_SCAN_LINES, totalLines);

  // 3. Parse each line — collect invalid and valid rows separately
  const invalidLineNums: number[] = [];
  const parsedRows: Array<{ lineNum: number; row: Record<string, unknown> }> = [];

  for (let i = 0; i < scanLines.length; i++) {
    try {
      const parsed: unknown = JSON.parse(scanLines[i]);
      if (parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)) {
        parsedRows.push({ lineNum: i + 1, row: parsed as Record<string, unknown> });
      } else {
        // Valid JSON but not an object (array, scalar, null) — not a valid JSONL dataset row
        invalidLineNums.push(i + 1);
      }
    } catch {
      invalidLineNums.push(i + 1);
    }
  }

  if (invalidLineNums.length > 0) {
    issues.push({
      severity: 'error',
      code: 'INVALID_JSON_LINES',
      message: `${plural(invalidLineNums.length, 'line')} could not be parsed as JSON objects.`,
      affectedLines: invalidLineNums.slice(0, MAX_AFFECTED_LINE_COUNT),
      count: invalidLineNums.length,
    });
  }

  if (parsedRows.length > 0) {
    // 4. Schema detection on the first valid row
    const firstRow = parsedRows[0].row;
    const hasMessagesSchema = findMessagesArray(firstRow) !== null;
    const hasPromptCompletionSchema =
      PROMPT_KEYS.some((k) => k in firstRow) || COMPLETION_KEYS.some((k) => k in firstRow);

    if (!hasMessagesSchema && !hasPromptCompletionSchema) {
      issues.push({
        severity: 'warning',
        code: 'UNKNOWN_SCHEMA',
        message:
          'No recognized fine-tuning schema detected. Expected a messages array or prompt/completion fields.',
      });
    }

    // 5. Null or empty field values across all valid rows
    const nullFieldLines: number[] = [];
    for (const { lineNum, row } of parsedRows) {
      const hasNullOrEmpty = Object.values(row).some(
        (v) => v === null || v === '' || (Array.isArray(v) && v.length === 0)
      );
      if (hasNullOrEmpty) nullFieldLines.push(lineNum);
    }
    if (nullFieldLines.length > 0) {
      issues.push({
        severity: 'warning',
        code: 'NULL_OR_EMPTY_FIELDS',
        message: `${plural(nullFieldLines.length, 'row')} contain null or empty field values.`,
        affectedLines: nullFieldLines.slice(0, MAX_AFFECTED_LINE_COUNT),
        count: nullFieldLines.length,
      });
    }

    // 6. Long entries — rough token estimate via character count
    const longLines: number[] = [];
    for (let i = 0; i < scanLines.length; i++) {
      if (scanLines[i].length > LONG_ENTRY_CHAR_THRESHOLD) {
        longLines.push(i + 1);
      }
    }
    if (longLines.length > 0) {
      issues.push({
        severity: 'warning',
        code: 'LONG_ENTRIES',
        message: `${plural(longLines.length, 'row')} may exceed the model's context window (~8,192 tokens).`,
        affectedLines: longLines.slice(0, MAX_AFFECTED_LINE_COUNT),
        count: longLines.length,
      });
    }
  }

  const hasErrors = issues.some((i) => i.severity === 'error');
  const hasWarnings = issues.some((i) => i.severity === 'warning');

  return { fileName: file.name, hasErrors, hasWarnings, issues, scannedLines, totalLines };
}
