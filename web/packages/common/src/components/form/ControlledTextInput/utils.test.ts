// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  stringToNumber,
  stringToInteger,
} from '@nemo/common/src/components/form/ControlledTextInput/utils';

describe('stringToNumber', () => {
  describe('valid inputs', () => {
    it('should convert valid numbers', () => {
      expect(stringToNumber('123')).toBe(123);
      expect(stringToNumber('-123')).toBe(-123);
      expect(stringToNumber('123.45')).toBe(123.45);
      expect(stringToNumber('-123.45')).toBe(-123.45);
      expect(stringToNumber('0')).toBe(0);
    });

    it('should convert scientific notation', () => {
      expect(stringToNumber('1e-15')).toBe(1e-15);
      expect(stringToNumber('1E-15')).toBe(1e-15);
      expect(stringToNumber('1.5e10')).toBe(1.5e10);
      expect(stringToNumber('-2.3e-5')).toBe(-2.3e-5);
      expect(stringToNumber('5e+3')).toBe(5e3);
      expect(stringToNumber('1e0')).toBe(1);
      expect(stringToNumber('0e0')).toBe(0);
    });
  });

  describe('invalid inputs without fallback', () => {
    it('should return undefined for invalid inputs', () => {
      expect(stringToNumber('')).toBeUndefined();
      expect(stringToNumber('   ')).toBeUndefined();
      expect(stringToNumber('abc')).toBeUndefined();
      expect(stringToNumber('123abc')).toBeUndefined();
    });

    it('should return undefined for invalid scientific notation', () => {
      expect(stringToNumber('e5')).toBeUndefined();
      expect(stringToNumber('1e')).toBeUndefined();
      expect(stringToNumber('1e+')).toBeUndefined();
      expect(stringToNumber('1e-')).toBeUndefined();
      expect(stringToNumber('1.2.3e5')).toBeUndefined();
      expect(stringToNumber('1ee5')).toBeUndefined();
      expect(stringToNumber('1e5.5')).toBeUndefined();
    });
  });

  describe('invalid inputs with fallback', () => {
    it('should return fallback for invalid inputs', () => {
      expect(stringToNumber('', 42)).toBe(42);
      expect(stringToNumber('abc', -1)).toBe(-1);
      expect(stringToNumber('   ', 100)).toBe(100);
    });
  });
});

describe('stringToInteger', () => {
  describe('valid inputs', () => {
    it('should convert valid integers', () => {
      expect(stringToInteger('123')).toBe(123);
      expect(stringToInteger('-123')).toBe(-123);
      expect(stringToInteger('0')).toBe(0);
    });

    it('should truncate decimals (not round)', () => {
      expect(stringToInteger('123.45')).toBe(123);
      expect(stringToInteger('-123.45')).toBe(-123);
      expect(stringToInteger('1.9')).toBe(1);
      expect(stringToInteger('-1.9')).toBe(-1);
    });
  });
});
