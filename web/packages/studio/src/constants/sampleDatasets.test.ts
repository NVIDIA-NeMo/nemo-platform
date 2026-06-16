// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  SAMPLE_DATASETS,
  SampleDataset,
  SampleDatasetFile,
} from '@studio/constants/sampleDatasets';
import { readFileSync, existsSync } from 'fs';
import { join } from 'path';

// Path to the public directory from this test file location
const PUBLIC_DIR = join(__dirname, '../../public');

describe('sampleDatasets', () => {
  describe('file existence', () => {
    // Test each dataset's files exist
    SAMPLE_DATASETS.forEach((dataset: SampleDataset) => {
      describe(`Dataset: ${dataset.name} (${dataset.id})`, () => {
        dataset.files.forEach((file: SampleDatasetFile) => {
          it(`should have file: ${file.path}`, () => {
            const fullPath = join(PUBLIC_DIR, file.path);

            expect(
              existsSync(fullPath),
              `File not found at path: ${fullPath}\n` +
                `Referenced in dataset "${dataset.name}" (${dataset.id})\n` +
                `Expected file: ${file.name}\n` +
                `Description: ${file.description || 'No description provided'}`
            ).toBe(true);
          });

          it(`should have readable file: ${file.path}`, () => {
            const fullPath = join(PUBLIC_DIR, file.path);

            expect(
              () => readFileSync(fullPath, 'utf8'),
              `File exists but is not readable: ${fullPath}`
            ).not.toThrow();
          });

          it(`should have non-empty file: ${file.path}`, () => {
            const fullPath = join(PUBLIC_DIR, file.path);
            const content = readFileSync(fullPath, 'utf8');

            expect(content.trim().length, `File is empty: ${fullPath}`).toBeGreaterThan(0);
          });
        });
      });
    });
  });

  describe('dataset structure validation', () => {
    it('should have at least one sample dataset', () => {
      expect(SAMPLE_DATASETS.length).toBeGreaterThan(0);
    });

    SAMPLE_DATASETS.forEach((dataset: SampleDataset) => {
      describe(`Dataset structure: ${dataset.id}`, () => {
        it('should have required properties', () => {
          expect(dataset.id).toBeDefined();
          expect(dataset.name).toBeDefined();
          expect(dataset.description).toBeDefined();
          expect(dataset.files).toBeDefined();
          expect(Array.isArray(dataset.files)).toBe(true);
        });

        it('should have at least one file', () => {
          expect(dataset.files.length).toBeGreaterThan(0);
        });

        dataset.files.forEach((file: SampleDatasetFile, index: number) => {
          it(`should have valid file structure for file ${index + 1}`, () => {
            expect(file.path).toBeDefined();
            expect(file.name).toBeDefined();
            expect(typeof file.path).toBe('string');
            expect(typeof file.name).toBe('string');
            expect(file.path.length).toBeGreaterThan(0);
            expect(file.name.length).toBeGreaterThan(0);
          });

          it(`should have path starting with 'sample-datasets/' for file ${index + 1}`, () => {
            expect(file.path).toMatch(/^sample-datasets\//);
          });
        });
      });
    });
  });

  describe('path consistency', () => {
    it('should have unique dataset IDs', () => {
      const allIds = SAMPLE_DATASETS.map((dataset: SampleDataset) => dataset.id);
      const uniqueIds = new Set(allIds);

      expect(uniqueIds.size).toBe(allIds.length);
    });
  });
});
