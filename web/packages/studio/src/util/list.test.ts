// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  SEQUENTIAL_DISTRIBUTION_ERROR_MESSAGE,
  splitRandomDistribution,
  splitSequentialDistribution,
} from '@studio/util/list';

describe('utils/list', () => {
  describe('splitRandomDistribution', () => {
    const arrayToSplit = [
      { id: 1 },
      { id: 2 },
      { id: 3 },
      { id: 4 },
      { id: 5 },
      { id: 6 },
      { id: 7 },
      { id: 8 },
      { id: 9 },
      { id: 10 },
    ];
    const splits = ['30%', 5, '20%'];
    it.each([
      ['30%', '50%', '20%'],
      [3, 5, 2],
      ['30%', 5, '20%'],
    ])('splits into random distribution', (...input) => {
      const randomDistribution = splitRandomDistribution(arrayToSplit, input);
      expect(randomDistribution).toHaveLength(3); // Three splits
      expect(randomDistribution[0]).toHaveLength(3);
      expect(randomDistribution[1]).toHaveLength(5);
      expect(randomDistribution[2]).toHaveLength(2);
    });

    it('should shuffle the array before splitting', () => {
      const originalArray = [...arrayToSplit];
      const result = splitRandomDistribution(arrayToSplit, splits);
      expect(result.every((split) => split.some((item) => !originalArray.includes(item)))).toBe(
        false
      ); // at least one item should be in a different position
    });

    it('should shuffle the array consistently when using a seed', () => {
      const result1 = splitRandomDistribution(arrayToSplit, splits, 'test');
      const result2 = splitRandomDistribution(arrayToSplit, splits, 'test');
      const result3 = splitRandomDistribution(arrayToSplit, splits, 'different seed');
      expect(result1).toEqual(result2);
      expect(result1).not.toEqual(result3);
      expect(result2).not.toEqual(result3);
    });

    it('should throw an error if countOrPercentage is not a non-empty array', () => {
      expect(() => splitRandomDistribution(arrayToSplit, [])).toThrowError(
        'splits must be a non-empty array.'
      );
    });

    it('should throw an error if total percentage exceeds 100%', () => {
      expect(() => splitRandomDistribution(arrayToSplit, ['120%', '200%'])).toThrowError(
        'Percentage values exceed 100%.'
      );
    });

    it('should throw an error if countOrPercentage has an invalid format', () => {
      expect(() => splitRandomDistribution(arrayToSplit, [' invalid format '])).toThrowError(
        'Invalid count or percentage format.'
      );
    });

    it('should throw an error if the total of counts + percentages are greater than total', () => {
      expect(() => splitRandomDistribution(arrayToSplit, ['99%', 4])).toThrowError(
        'Sum of splits is greater than total items.'
      );
    });
  });

  describe('splitSequentialDistribution', () => {
    it('should split the array into a given number of parts using a sequential distribution', () => {
      const array = [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }, { id: 5 }];
      const splits = [1, 3, 1];
      const result = splitSequentialDistribution(array, splits);
      expect(result).toHaveLength(3);
      expect(result[0]).toHaveLength(splits[0]);
      expect(result[1]).toHaveLength(splits[1]);
      expect(result[2]).toHaveLength(splits[2]);
    });

    it('should sort the array by the chosen key before splitting', () => {
      const array = [{ id: 3 }, { id: 4 }, { id: 5 }, { id: 1 }, { id: 2 }];
      const splits = [1, 3, 1];
      const result = splitSequentialDistribution(array, splits, {
        key: 'id',
        direction: 'desc',
      });
      expect(result[0]).toEqual([{ id: 5 }]);
      expect(result[1]).toEqual([{ id: 4 }, { id: 3 }, { id: 2 }]);
      expect(result[2]).toEqual([{ id: 1 }]);
    });

    it('should handle sorting the array by dates', () => {
      const array = [
        { date: new Date('2021-01-01') },
        { date: new Date('2021-01-02') },
        { date: new Date('2021-01-03') },
        { date: new Date('2021-01-04') },
        { date: new Date('2021-01-05') },
      ];
      const splits = [1, 3, 1];
      const result = splitSequentialDistribution(array, splits, {
        direction: 'asc',
      });
      expect(result[0]).toEqual([{ date: new Date('2021-01-01') }]);
      expect(result[1]).toEqual([
        { date: new Date('2021-01-02') },
        { date: new Date('2021-01-03') },
        { date: new Date('2021-01-04') },
      ]);
      expect(result[2]).toEqual([{ date: new Date('2021-01-05') }]);
    });

    it('should sort using a user defined sort key', () => {
      const array = [{ test: 3 }, { test: 4 }, { test: 5 }, { test: 1 }, { test: 2 }];
      const splits = [1, 3, 1];
      const result = splitSequentialDistribution(array, splits, {
        key: 'test',
      });
      expect(result[0]).toEqual([{ test: 1 }]);
      expect(result[1]).toEqual([{ test: 2 }, { test: 3 }, { test: 4 }]);
      expect(result[2]).toEqual([{ test: 5 }]);
    });

    it('should throw an error if no default sortable key is found', () => {
      const array = [{ key: 1 }, { key: 2 }, { key: 3 }, { key: 4 }, { key: 5 }];
      const splits = [1, 3, 1];
      expect(() => splitSequentialDistribution(array, splits)).toThrowError(
        SEQUENTIAL_DISTRIBUTION_ERROR_MESSAGE
      );
    });
  });
});
