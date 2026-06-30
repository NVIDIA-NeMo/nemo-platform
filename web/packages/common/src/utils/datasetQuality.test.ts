// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { checkDatasetQuality } from '@nemo/common/src/utils/datasetQuality';

function makeFile(content: string, name = 'train.jsonl', bytes?: Uint8Array): File {
  const file = new File([content], name, { type: 'application/x-jsonlines' });
  file.text = vi.fn().mockResolvedValue(content);
  file.arrayBuffer = vi
    .fn()
    .mockResolvedValue(bytes ? bytes.buffer : new TextEncoder().encode(content).buffer);
  return file;
}

function utf16File(content: string, le = true): File {
  const bom = le ? new Uint8Array([0xff, 0xfe]) : new Uint8Array([0xfe, 0xff]);
  const encoded = new TextEncoder().encode(content);
  const merged = new Uint8Array(bom.length + encoded.length);
  merged.set(bom);
  merged.set(encoded, bom.length);
  return makeFile(content, 'train.jsonl', merged);
}

function jsonlLines(rows: object[]): string {
  return rows.map((r) => JSON.stringify(r)).join('\n');
}

describe('checkDatasetQuality', () => {
  describe('encoding', () => {
    it('returns INVALID_ENCODING error for UTF-16 LE', async () => {
      const report = await checkDatasetQuality(utf16File('some content', true));
      expect(report.hasErrors).toBe(true);
      expect(report.issues[0].code).toBe('INVALID_ENCODING');
      expect(report.issues[0].severity).toBe('error');
    });

    it('returns INVALID_ENCODING error for UTF-16 BE', async () => {
      const report = await checkDatasetQuality(utf16File('some content', false));
      expect(report.hasErrors).toBe(true);
      expect(report.issues[0].code).toBe('INVALID_ENCODING');
    });

    it('does not flag UTF-8 files', async () => {
      const file = makeFile(
        jsonlLines([
          {
            messages: [
              { role: 'user', content: 'hi' },
              { role: 'assistant', content: 'hello' },
            ],
          },
        ])
      );
      const report = await checkDatasetQuality(file);
      expect(report.issues.find((i) => i.code === 'INVALID_ENCODING')).toBeUndefined();
    });
  });

  describe('empty file', () => {
    it('returns EMPTY_FILE error for blank file', async () => {
      const report = await checkDatasetQuality(makeFile(''));
      expect(report.hasErrors).toBe(true);
      expect(report.issues[0].code).toBe('EMPTY_FILE');
    });

    it('returns EMPTY_FILE error for whitespace-only file', async () => {
      const report = await checkDatasetQuality(makeFile('   \n\t\n  '));
      expect(report.hasErrors).toBe(true);
      expect(report.issues[0].code).toBe('EMPTY_FILE');
    });
  });

  describe('JSON parsing', () => {
    it('returns INVALID_JSON_LINES error for malformed lines', async () => {
      const content = jsonlLines([{ prompt: 'q', completion: 'a' }]) + '\nnot-json\nalso bad';
      const report = await checkDatasetQuality(makeFile(content));
      const issue = report.issues.find((i) => i.code === 'INVALID_JSON_LINES');
      expect(issue).toBeDefined();
      expect(issue?.severity).toBe('error');
      expect(issue?.count).toBe(2);
      expect(issue?.affectedLines).toContain(2);
      expect(issue?.affectedLines).toContain(3);
    });

    it('flags JSON arrays and scalars as invalid lines (not JSON objects)', async () => {
      const content = '["not", "an", "object"]\n42';
      const report = await checkDatasetQuality(makeFile(content));
      const issue = report.issues.find((i) => i.code === 'INVALID_JSON_LINES');
      expect(issue?.count).toBe(2);
    });

    it('has no parse error for valid JSONL', async () => {
      const content = jsonlLines([
        { prompt: 'q', completion: 'a' },
        { prompt: 'q2', completion: 'a2' },
      ]);
      const report = await checkDatasetQuality(makeFile(content));
      expect(report.issues.find((i) => i.code === 'INVALID_JSON_LINES')).toBeUndefined();
    });
  });

  describe('schema detection', () => {
    it('no warning for messages schema', async () => {
      const row = {
        messages: [
          { role: 'user', content: 'hi' },
          { role: 'assistant', content: 'hello' },
        ],
      };
      const report = await checkDatasetQuality(makeFile(jsonlLines([row])));
      expect(report.issues.find((i) => i.code === 'UNKNOWN_SCHEMA')).toBeUndefined();
    });

    it('no warning for prompt/completion schema', async () => {
      const report = await checkDatasetQuality(
        makeFile(jsonlLines([{ prompt: 'q', completion: 'a' }]))
      );
      expect(report.issues.find((i) => i.code === 'UNKNOWN_SCHEMA')).toBeUndefined();
    });

    it('no warning for question/ideal_response schema', async () => {
      const report = await checkDatasetQuality(
        makeFile(jsonlLines([{ question: 'q', ideal_response: 'a' }]))
      );
      expect(report.issues.find((i) => i.code === 'UNKNOWN_SCHEMA')).toBeUndefined();
    });

    it('returns UNKNOWN_SCHEMA warning for unrecognized fields', async () => {
      // None of these keys match known schema patterns (no messages, prompt, completion, etc.)
      const report = await checkDatasetQuality(
        makeFile(jsonlLines([{ topic: 'foo', category: 'bar', label: 1 }]))
      );
      const issue = report.issues.find((i) => i.code === 'UNKNOWN_SCHEMA');
      expect(issue).toBeDefined();
      expect(issue?.severity).toBe('warning');
    });
  });

  describe('null and empty fields', () => {
    it('returns NULL_OR_EMPTY_FIELDS warning for null values', async () => {
      const content = jsonlLines([
        { prompt: 'q', completion: null },
        { prompt: 'q2', completion: 'a2' },
      ]);
      const report = await checkDatasetQuality(makeFile(content));
      const issue = report.issues.find((i) => i.code === 'NULL_OR_EMPTY_FIELDS');
      expect(issue).toBeDefined();
      expect(issue?.count).toBe(1);
      expect(issue?.affectedLines).toContain(1);
    });

    it('returns NULL_OR_EMPTY_FIELDS warning for empty string values', async () => {
      const content = jsonlLines([{ prompt: '', completion: 'a' }]);
      const report = await checkDatasetQuality(makeFile(content));
      expect(report.issues.find((i) => i.code === 'NULL_OR_EMPTY_FIELDS')).toBeDefined();
    });

    it('returns NULL_OR_EMPTY_FIELDS warning for empty arrays', async () => {
      const content = jsonlLines([{ messages: [] }]);
      const report = await checkDatasetQuality(makeFile(content));
      expect(report.issues.find((i) => i.code === 'NULL_OR_EMPTY_FIELDS')).toBeDefined();
    });

    it('no warning when all fields are populated', async () => {
      const content = jsonlLines([{ prompt: 'q', completion: 'a' }]);
      const report = await checkDatasetQuality(makeFile(content));
      expect(report.issues.find((i) => i.code === 'NULL_OR_EMPTY_FIELDS')).toBeUndefined();
    });
  });

  describe('long entries', () => {
    it('returns LONG_ENTRIES warning when a line exceeds 32768 chars', async () => {
      const longValue = 'x'.repeat(33_000);
      const content = jsonlLines([{ prompt: longValue, completion: 'a' }]);
      const report = await checkDatasetQuality(makeFile(content));
      const issue = report.issues.find((i) => i.code === 'LONG_ENTRIES');
      expect(issue).toBeDefined();
      expect(issue?.severity).toBe('warning');
      expect(issue?.affectedLines).toContain(1);
    });

    it('no warning for normal-length lines', async () => {
      const content = jsonlLines([{ prompt: 'short question', completion: 'short answer' }]);
      const report = await checkDatasetQuality(makeFile(content));
      expect(report.issues.find((i) => i.code === 'LONG_ENTRIES')).toBeUndefined();
    });
  });

  describe('line scanning limit', () => {
    it('scans only first 1000 lines for large files', async () => {
      const rows = Array.from({ length: 1500 }, (_, i) => ({
        prompt: `q${i}`,
        completion: `a${i}`,
      }));
      const content = jsonlLines(rows);
      const report = await checkDatasetQuality(makeFile(content));
      expect(report.totalLines).toBe(1500);
      expect(report.scannedLines).toBe(1000);
    });
  });

  describe('report structure', () => {
    it('sets hasErrors and hasWarnings correctly', async () => {
      const content = jsonlLines([{ prompt: 'q', completion: 'a' }]);
      const report = await checkDatasetQuality(makeFile(content));
      expect(report.hasErrors).toBe(false);
      expect(report.hasWarnings).toBe(false);
      expect(report.fileName).toBe('train.jsonl');
    });

    it('caps affectedLines at 10 entries', async () => {
      const rows = Array.from({ length: 15 }, () => ({ prompt: '', completion: '' }));
      const content = jsonlLines(rows);
      const report = await checkDatasetQuality(makeFile(content));
      const issue = report.issues.find((i) => i.code === 'NULL_OR_EMPTY_FIELDS');
      expect(issue?.affectedLines?.length).toBeLessThanOrEqual(10);
      expect(issue?.count).toBe(15);
    });
  });
});
