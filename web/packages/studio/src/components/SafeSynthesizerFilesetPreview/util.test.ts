// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { parseFilesetUrl } from '@nemo/common/src/components/DatasetFileSelect/utils';
import { parseCSV, parseFileContent } from '@studio/components/SafeSynthesizerFilesetPreview/util';

vi.mock('papaparse', () => ({
  default: {
    parse: vi.fn(),
  },
}));

const { default: Papa } = await import('papaparse');
const mockPapaParse = vi.mocked(Papa.parse);

describe('SafeSynthesizerDatasetPreview utils', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('parseCSV', () => {
    it('should parse CSV content and return rows and columns', () => {
      const mockCsvContent = 'name,age,city\nJohn,30,NYC\nJane,25,LA';
      const mockParsedData: Papa.ParseResult<Record<string, unknown>> = {
        data: [
          { name: 'John', age: '30', city: 'NYC' },
          { name: 'Jane', age: '25', city: 'LA' },
        ],
        meta: {
          fields: ['name', 'age', 'city'],
          delimiter: ',',
          linebreak: '\n',
          aborted: false,
          truncated: false,
          cursor: 0,
        },
        errors: [],
      };

      mockPapaParse.mockImplementation(vi.fn().mockReturnValue(mockParsedData));

      const result = parseCSV(mockCsvContent);

      expect(mockPapaParse).toHaveBeenCalledWith(mockCsvContent, { header: true });
      expect(result.columns).toEqual([
        { children: 'name' },
        { children: 'age' },
        { children: 'city' },
      ]);
      expect(result.rows).toHaveLength(2);
      expect(result.rows[0].cells).toEqual([
        { children: 'John' },
        { children: '30' },
        { children: 'NYC' },
      ]);
    });

    it('should use row id if available', () => {
      const mockParsedData: Papa.ParseResult<Record<string, unknown>> = {
        data: [{ id: 'custom-id', name: 'John' }],
        meta: {
          fields: ['id', 'name'],
          delimiter: ',',
          linebreak: '\n',
          aborted: false,
          truncated: false,
          cursor: 0,
        },
        errors: [],
      };

      mockPapaParse.mockImplementation(vi.fn().mockReturnValue(mockParsedData));

      const result = parseCSV('id,name\ncustom-id,John');

      expect(result.rows[0].id).toBe('custom-id');
    });

    it('should use index as id if row id is not available', () => {
      const mockParsedData: Papa.ParseResult<Record<string, unknown>> = {
        data: [{ name: 'John' }, { name: 'Jane' }],
        meta: {
          fields: ['name'],
          delimiter: ',',
          linebreak: '\n',
          aborted: false,
          truncated: false,
          cursor: 0,
        },
        errors: [],
      };

      mockPapaParse.mockImplementation(vi.fn().mockReturnValue(mockParsedData));

      const result = parseCSV('name\nJohn\nJane');

      expect(result.rows[0].id).toBe('0');
      expect(result.rows[1].id).toBe('1');
    });

    it('should handle empty values', () => {
      const mockParsedData: Papa.ParseResult<Record<string, unknown>> = {
        data: [{ name: 'John', age: null, city: undefined }],
        meta: {
          fields: ['name', 'age', 'city'],
          delimiter: ',',
          linebreak: '\n',
          aborted: false,
          truncated: false,
          cursor: 0,
        },
        errors: [],
      };

      mockPapaParse.mockImplementation(vi.fn().mockReturnValue(mockParsedData));

      const result = parseCSV('name,age,city\nJohn,,');

      expect(result.rows[0].cells[1].children).toBe('');
      expect(result.rows[0].cells[2].children).toBe('');
    });
  });

  describe('parseFilesetUrl', () => {
    it('should parse fileset URL correctly', () => {
      const url = 'fileset://my-workspace/my-dataset/train.jsonl';
      const result = parseFilesetUrl(url);

      expect(result).toEqual({
        workspace: 'my-workspace',
        name: 'my-dataset',
        path: 'train.jsonl',
      });
    });

    it('should handle nested file paths', () => {
      const url = 'fileset://workspace/dataset/folder/subfolder/file.csv';
      const result = parseFilesetUrl(url);

      expect(result).toEqual({
        workspace: 'workspace',
        name: 'dataset',
        path: 'folder/subfolder/file.csv',
      });
    });

    it('should return null for invalid fileset URL', () => {
      const url = 'hf://datasets/org/repo/file.csv';
      const result = parseFilesetUrl(url);

      expect(result).toBeNull();
    });

    it('should return null for malformed fileset URL', () => {
      const url = 'fileset://workspace';
      const result = parseFilesetUrl(url);

      expect(result).toBeNull();
    });
  });

  describe('parseFileContent', () => {
    beforeEach(() => {
      // Reset Papa.parse mock for parseFileContent tests
      const mockParsedData: Papa.ParseResult<Record<string, unknown>> = {
        data: [{ col1: 'value1' }],
        meta: {
          fields: ['col1'],
          delimiter: ',',
          linebreak: '\n',
          aborted: false,
          truncated: false,
          cursor: 0,
        },
        errors: [],
      };
      mockPapaParse.mockImplementation(vi.fn().mockReturnValue(mockParsedData));
    });

    it('should parse CSV files', () => {
      const content = 'name,age\nJohn,30';

      const mockParsedData: Papa.ParseResult<Record<string, unknown>> = {
        data: [{ name: 'John', age: '30' }],
        meta: {
          fields: ['name', 'age'],
          delimiter: ',',
          linebreak: '\n',
          aborted: false,
          truncated: false,
          cursor: 0,
        },
        errors: [],
      };
      mockPapaParse.mockImplementation(vi.fn().mockReturnValue(mockParsedData));

      const result = parseFileContent('data.csv', content);

      expect(result.type).toBe('csv');
      expect(result.tabularData).toBeDefined();
      expect(result.tabularData?.columns).toHaveLength(2);
      expect(result.jsonData).toBeUndefined();
      expect(result.error).toBeUndefined();
    });

    it('should parse JSON files', () => {
      const content = '{"name": "John", "age": 30}';
      const result = parseFileContent('data.json', content);

      expect(result.type).toBe('json');
      expect(result.jsonData).toBe(content);
      expect(result.tabularData).toBeUndefined();
      expect(result.error).toBeUndefined();
    });

    it('should parse JSONL files', () => {
      const content = '{"name": "John"}\n{"name": "Jane"}';
      const result = parseFileContent('data.jsonl', content);

      expect(result.type).toBe('json');
      expect(result.jsonData).toBe(content);
      expect(result.tabularData).toBeUndefined();
      expect(result.error).toBeUndefined();
    });

    it('should return error for unsupported file types', () => {
      const content = 'some content';
      const result = parseFileContent('data.txt', content);

      expect(result.type).toBe('error');
      expect(result.error).toBe('Unsupported file type');
      expect(result.tabularData).toBeUndefined();
      expect(result.jsonData).toBeUndefined();
    });

    it('should handle paths with multiple dots', () => {
      const content = 'col1\nvalue1';
      const result = parseFileContent('my.data.file.csv', content);

      expect(result.type).toBe('csv');
      expect(result.tabularData).toBeDefined();
    });

    it('should handle full paths with directories', () => {
      const jsonContent = '{"test": true}';
      const result = parseFileContent('folder/subfolder/data.json', jsonContent);

      expect(result.type).toBe('json');
      expect(result.jsonData).toBe(jsonContent);
    });
  });
});
