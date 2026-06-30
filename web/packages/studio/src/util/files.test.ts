// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ContentType } from '@nemo/common/src/components/CodeEditor/constants';
import {
  collectFolderPathsFromDatasetFiles,
  getContentSchema,
  getDatasetDisplayNameFromFilesUrl,
  getFileNameFromPath,
  getFolderSize,
  inferJsonContentType,
  isJsonFile,
  resolveDatasetFilePath,
} from '@studio/util/files';

describe('getContentSchema', () => {
  it.each([undefined, ''])('returns empty schema', (input) => {
    expect(getContentSchema(input)).toEqual({});
  });

  it('parses single row and extracts schema', () => {
    const content = '{"key1": "value1", "key2": 2}';
    const expectedSchema = { schema: { key1: 'string', key2: 'number' }, total_rows: 1 };
    expect(getContentSchema(content)).toEqual(expectedSchema);
  });

  it('parses multiple rows and extracts schema', () => {
    const content = '{"key1": "value1", "key2": 2}\n{"key1": "value3", "key3": true}\n';
    const expectedSchema = {
      schema: { key1: 'string', key2: 'number', key3: 'boolean' },
      total_rows: 2,
    };
    expect(getContentSchema(content, { all: true })).toEqual(expectedSchema);
  });

  it('parses row with inconsistent schema', () => {
    const content = '{"key1": "value1", "key2": 2}\n{"key1": 3, "key2": "value3"}\n';
    const expectedSchema = {
      schema: { key1: 'mixed', key2: 'mixed' },
      total_rows: 2,
    };
    expect(getContentSchema(content, { all: true })).toEqual(expectedSchema);
  });

  it("parses rows with object values and extracts schema as 'object'", () => {
    const content = '{"key1": {"key2": "value2"}}';
    const expectedSchema = {
      schema: { key1: 'object' },
      total_rows: 1,
    };
    expect(getContentSchema(content)).toEqual(expectedSchema);
  });

  it('parses rows with array values and extracts schema as "array"', () => {
    const content = '{"key1": ["value1"]}';
    const expectedSchema = {
      schema: { key1: 'array' },
      total_rows: 1,
    };
    expect(getContentSchema(content)).toEqual(expectedSchema);
  });

  it('parses row with multiple schemas', () => {
    const content = '{"key1": "value1", "key2": 2, "key3": {"key4": "value4"}}';
    const expectedSchema = {
      schema: { key1: 'string', key2: 'number', key3: 'object' },
      total_rows: 1,
    };
    expect(getContentSchema(content)).toEqual(expectedSchema);
  });

  it('parses rows with oneRow option enabled', () => {
    const content = '{"key1": "value1", "key2": 2}\n{"key1": "value3", "key3": true}\n';
    const expectedSchema = {
      schema: { key1: 'string', key2: 'number' },
      total_rows: 2,
    };
    expect(getContentSchema(content)).toEqual(expectedSchema);
  });

  it('pads JSON parsing exceptions and skips rows', () => {
    const content = '{"key1": "value1"}\n{ invalid JSON }\n{"key2": "value2"}\n';
    const expectedSchema = {
      schema: { key1: 'string', key2: 'string' },
      total_rows: 2,
    };
    // Spy on console.warn
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(getContentSchema(content, { all: true })).toEqual(expectedSchema);
    expect(warnSpy).toHaveBeenCalledTimes(1);
    expect(warnSpy).toHaveBeenCalledWith('Invalid JSON row ignored: { invalid JSON }');
  });
});

describe('getFileNameFromPath', () => {
  it('returns the correct file name', () => {
    const fileName = 'training_file.jsonl';

    expect(getFileNameFromPath('')).toEqual('');
    expect(getFileNameFromPath(fileName)).toEqual(fileName);
    expect(getFileNameFromPath(`/${fileName}`)).toEqual(fileName);
    expect(getFileNameFromPath(`/training/${fileName}`)).toEqual(fileName);
    expect(getFileNameFromPath(`/training/nested_folder/${fileName}`)).toEqual(fileName);
  });
});

describe('inferJsonContentType', () => {
  describe('JSON files', () => {
    it('should return ContentType.JSON for .json files', () => {
      expect(inferJsonContentType('data.json')).toBe(ContentType.JSON);
      expect(inferJsonContentType('data.JSON')).toBe(ContentType.JSON);
      expect(inferJsonContentType('file.Json')).toBe(ContentType.JSON);
      expect(inferJsonContentType('/path/to/data.json')).toBe(ContentType.JSON);
      expect(inferJsonContentType('./relative/path/file.json')).toBe(ContentType.JSON);
      expect(inferJsonContentType('folder/subfolder/config.json')).toBe(ContentType.JSON);
      expect(inferJsonContentType('file with spaces.json')).toBe(ContentType.JSON);
      expect(inferJsonContentType('file-with-dashes.jsonl')).toBe(ContentType.JSONL);
      expect(inferJsonContentType('file_with_underscores.json')).toBe(ContentType.JSON);
    });
  });

  describe('JSONL files', () => {
    it('should return ContentType.JSONL for .jsonl files', () => {
      expect(inferJsonContentType('data.jsonl')).toBe(ContentType.JSONL);
      expect(inferJsonContentType('data.JSONL')).toBe(ContentType.JSONL);
      expect(inferJsonContentType('config.Jsonl')).toBe(ContentType.JSONL);
      expect(inferJsonContentType('/path/to/data.jsonl')).toBe(ContentType.JSONL);
      expect(inferJsonContentType('./relative/path/file.jsonl')).toBe(ContentType.JSONL);
      expect(inferJsonContentType('folder/subfolder/config.jsonl')).toBe(ContentType.JSONL);
    });
  });

  describe('Non-JSON files', () => {
    it('should return null for files with other extensions', () => {
      expect(inferJsonContentType('data.txt')).toBe(null);
      expect(inferJsonContentType('file.csv')).toBe(null);
      expect(inferJsonContentType('file.tar.gz')).toBe(null);
      expect(inferJsonContentType('archive.zip.bak')).toBe(null);
      expect(inferJsonContentType('myfile')).toBe(null);
      expect(inferJsonContentType('README')).toBe(null);
      expect(inferJsonContentType('Makefile')).toBe(null);
    });

    it('should return null for empty string', () => {
      expect(inferJsonContentType('')).toBe(null);
    });
  });

  describe('Edge cases', () => {
    it('should handle files with json/jsonl in the middle of the name', () => {
      expect(inferJsonContentType('myjsonfile.txt')).toBe(null);
      expect(inferJsonContentType('datajsonl.csv')).toBe(null);
      expect(inferJsonContentType('jsonconfig.xml')).toBe(null);
      expect(inferJsonContentType('json')).toBe(null);
    });
  });
});

describe('isJsonFile', () => {
  it('should return true for JSON or JSONLcontent type', () => {
    expect(isJsonFile(ContentType.JSON)).toBe(true);
    expect(isJsonFile(ContentType.JSONL)).toBe(true);
  });

  it('should return false for null or undefined content type', () => {
    expect(isJsonFile(null)).toBe(false);
    expect(isJsonFile(undefined as unknown as ContentType | null)).toBe(false);
  });
});

describe('getDatasetDisplayNameFromFilesUrl', () => {
  it('should extract dataset name and file from HuggingFace URL', () => {
    const result = getDatasetDisplayNameFromFilesUrl(
      'hf://datasets/test-user/my-dataset/data.jsonl'
    );
    expect(result).toBe('my-dataset/data.jsonl');
  });

  it('should extract last two segments from NDS URL', () => {
    const result = getDatasetDisplayNameFromFilesUrl('nds:namespace/dataset-name/validation.json');
    expect(result).toBe('dataset-name/validation.json');
  });

  it('should return undefined for undefined input', () => {
    const result = getDatasetDisplayNameFromFilesUrl(undefined);
    expect(result).toBeUndefined();
  });

  it('should return original URL if fewer than 2 segments', () => {
    const result = getDatasetDisplayNameFromFilesUrl('single-segment');
    expect(result).toBe('single-segment');
  });
});

describe('getFolderSize', () => {
  it('should return the correct folder size', () => {
    const folder = {
      type: 'directory' as const,
      size: 0,
      path: '',
      oid: '',
      children: {
        file1: { type: 'file' as const, size: 100, path: 'file1.txt', oid: 'oid1' },
        file2: { type: 'file' as const, size: 200, path: 'file2.txt', oid: 'oid2' },
        folder1: {
          type: 'directory' as const,
          size: 0,
          path: 'folder1',
          oid: 'oid1',
          children: {
            file3: { type: 'file' as const, size: 300, path: 'file3.txt', oid: 'oid3' },
            folder2: {
              type: 'directory' as const,
              size: 0,
              path: 'folder2',
              oid: 'oid2',
              children: {
                file4: { type: 'file' as const, size: 400, path: 'file4.txt', oid: 'oid4' },
              },
            },
          },
        },
      },
    };
    expect(getFolderSize(folder)).toBe('1,000B (4 files)');
  });
});

describe('resolveDatasetFilePath', () => {
  it('returns multi-segment paths unchanged', () => {
    expect(resolveDatasetFilePath('a/b/c.txt', 'a')).toBe('a/b/c.txt');
    expect(resolveDatasetFilePath('training/data/file.json', 'training')).toBe(
      'training/data/file.json'
    );
  });

  it('joins single-segment paths with folder', () => {
    expect(resolveDatasetFilePath('file.txt', 'training')).toBe('training/file.txt');
    expect(resolveDatasetFilePath('file.txt', 'training/')).toBe('training/file.txt');
  });

  it('returns basename-only path when folder is undefined', () => {
    expect(resolveDatasetFilePath('readme.txt', undefined)).toBe('readme.txt');
  });

  it('treats empty string folder like undefined for single-segment paths', () => {
    expect(resolveDatasetFilePath('readme.txt', '')).toBe('readme.txt');
    expect(resolveDatasetFilePath('file.txt', '')).toBe('file.txt');
  });

  it('returns multi-segment paths unchanged when folder is empty string', () => {
    expect(resolveDatasetFilePath('a/b/c.txt', '')).toBe('a/b/c.txt');
  });
});

describe('collectFolderPathsFromDatasetFiles', () => {
  it('returns empty for undefined or empty input', () => {
    expect(collectFolderPathsFromDatasetFiles(undefined)).toEqual([]);
    expect(collectFolderPathsFromDatasetFiles([])).toEqual([]);
  });

  it('returns empty when all files are at root', () => {
    expect(collectFolderPathsFromDatasetFiles([{ path: 'a.txt' }, { path: 'b.txt' }])).toEqual([]);
  });

  it('collects sorted unique folder prefixes', () => {
    expect(
      collectFolderPathsFromDatasetFiles([
        { path: 'a/b/c.txt' },
        { path: 'a/d.txt' },
        { path: 'root.txt' },
      ])
    ).toEqual(['a', 'a/b']);
  });
});
