// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { importFileContentSchema } from '@studio/components/ImportFileContent/validation';

describe('importFileContentSchema', () => {
  describe('file field validation', () => {
    it('should accept files with allowed extensions (json, jsonl, csv, parquet)', () => {
      const jsonFile = new File(['{}'], 'test.json', { type: 'application/json' });
      const result = importFileContentSchema.safeParse({ file: jsonFile });
      expect(result.success).toBe(true);

      const jsonlFile = new File(['{}'], 'test.jsonl', { type: 'application/json' });
      const jsonlResult = importFileContentSchema.safeParse({ file: jsonlFile });
      expect(jsonlResult.success).toBe(true);

      const csvFile = new File(['a,b,c'], 'test.csv', { type: 'text/csv' });
      const csvResult = importFileContentSchema.safeParse({ file: csvFile });
      expect(csvResult.success).toBe(true);

      const parquetFile = new File([''], 'test.parquet', { type: 'application/octet-stream' });
      const parquetResult = importFileContentSchema.safeParse({ file: parquetFile });
      expect(parquetResult.success).toBe(true);
    });

    it('should reject files with disallowed extensions (.txt)', () => {
      const txtFile = new File(['some text'], 'test.txt', { type: 'text/plain' });
      const result = importFileContentSchema.safeParse({ file: txtFile });

      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.errors[0].message).toContain('Unsupported file type');
        expect(result.error.errors[0].message).toContain('csv, json, jsonl, parquet');
      }
    });

    it('should reject files with other disallowed extensions', () => {
      const extensions = ['.pdf', '.docx', '.xlsx', '.zip', '.tar.gz'];

      extensions.forEach((ext) => {
        const file = new File(['content'], `test${ext}`, { type: 'application/octet-stream' });
        const result = importFileContentSchema.safeParse({ file });

        expect(result.success).toBe(false);
        if (!result.success) {
          expect(result.error.errors[0].message).toContain('Unsupported file type');
        }
      });
    });

    it('should allow undefined file (optional field)', () => {
      const result = importFileContentSchema.safeParse({ file: undefined });
      expect(result.success).toBe(true);
    });
  });

  describe('filepath field validation', () => {
    it('should accept filepaths with allowed extensions', () => {
      const result = importFileContentSchema.safeParse({
        datasetId: 'default/dataset',
        filepath: 'path/to/file.json',
      });
      expect(result.success).toBe(true);

      const jsonlResult = importFileContentSchema.safeParse({
        datasetId: 'default/dataset',
        filepath: 'data/examples.jsonl',
      });
      expect(jsonlResult.success).toBe(true);

      const csvResult = importFileContentSchema.safeParse({
        datasetId: 'default/dataset',
        filepath: 'table.csv',
      });
      expect(csvResult.success).toBe(true);

      const parquetResult = importFileContentSchema.safeParse({
        datasetId: 'default/dataset',
        filepath: 'data.parquet',
      });
      expect(parquetResult.success).toBe(true);
    });

    it('should reject filepaths with disallowed extensions (.txt)', () => {
      const result = importFileContentSchema.safeParse({
        datasetId: 'default/dataset',
        filepath: 'notes/random.txt',
      });

      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.errors[0].message).toContain('Unsupported file type');
        expect(result.error.errors[0].message).toContain('csv, json, jsonl, parquet');
      }
    });

    it('should reject filepaths with other disallowed extensions', () => {
      const filepaths = [
        'document.pdf',
        'spreadsheet.xlsx',
        'archive.zip',
        'image.png',
        'readme.md',
      ];

      filepaths.forEach((filepath) => {
        const result = importFileContentSchema.safeParse({
          datasetId: 'default/dataset',
          filepath,
        });

        expect(result.success).toBe(false);
        if (!result.success) {
          expect(result.error.errors[0].message).toContain('Unsupported file type');
        }
      });
    });

    it('should allow undefined filepath (optional field)', () => {
      const result = importFileContentSchema.safeParse({
        datasetId: 'default/dataset',
        filepath: undefined,
      });
      expect(result.success).toBe(true);
    });
  });

  describe('combined validation', () => {
    it('should validate both file and filepath can coexist', () => {
      const file = new File(['{}'], 'local.json', { type: 'application/json' });
      const result = importFileContentSchema.safeParse({
        file,
        datasetId: 'default/dataset',
        filepath: 'remote.json',
      });
      expect(result.success).toBe(true);
    });

    it('should allow empty form data', () => {
      const result = importFileContentSchema.safeParse({});
      expect(result.success).toBe(true);
    });
  });
});
