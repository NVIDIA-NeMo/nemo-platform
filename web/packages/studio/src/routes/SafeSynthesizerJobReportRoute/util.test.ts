// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  GRADE_VALUES,
  getDataPrivacyGradeLabel,
  getSyntheticQualityGradeLabel,
  GRADE_ORDER,
  isPassingGrade,
} from '@studio/routes/SafeSynthesizerJobReportRoute/util';

describe('SafeSynthesizerJobReportRoute utils', () => {
  describe('getDataPrivacyGradeLabel', () => {
    it('returns "Poor" for scores less than 2', () => {
      expect(getDataPrivacyGradeLabel(0)).toBe(GRADE_VALUES.POOR);
      expect(getDataPrivacyGradeLabel(1)).toBe(GRADE_VALUES.POOR);
      expect(getDataPrivacyGradeLabel(1.99)).toBe(GRADE_VALUES.POOR);
    });

    it('returns "Moderate" for scores between 2 and 3.99', () => {
      expect(getDataPrivacyGradeLabel(2)).toBe(GRADE_VALUES.MODERATE);
      expect(getDataPrivacyGradeLabel(3)).toBe(GRADE_VALUES.MODERATE);
      expect(getDataPrivacyGradeLabel(3.99)).toBe(GRADE_VALUES.MODERATE);
    });

    it('returns "Good" for scores between 4 and 5.99', () => {
      expect(getDataPrivacyGradeLabel(4)).toBe(GRADE_VALUES.GOOD);
      expect(getDataPrivacyGradeLabel(5)).toBe(GRADE_VALUES.GOOD);
      expect(getDataPrivacyGradeLabel(5.99)).toBe(GRADE_VALUES.GOOD);
    });

    it('returns "Very Good" for scores between 6 and 7.99', () => {
      expect(getDataPrivacyGradeLabel(6)).toBe(GRADE_VALUES.VERY_GOOD);
      expect(getDataPrivacyGradeLabel(7)).toBe(GRADE_VALUES.VERY_GOOD);
      expect(getDataPrivacyGradeLabel(7.99)).toBe(GRADE_VALUES.VERY_GOOD);
    });

    it('returns "Excellent" for scores 8 and above', () => {
      expect(getDataPrivacyGradeLabel(8)).toBe(GRADE_VALUES.EXCELLENT);
      expect(getDataPrivacyGradeLabel(9)).toBe(GRADE_VALUES.EXCELLENT);
      expect(getDataPrivacyGradeLabel(10)).toBe(GRADE_VALUES.EXCELLENT);
      expect(getDataPrivacyGradeLabel(100)).toBe(GRADE_VALUES.EXCELLENT);
    });

    it('handles edge cases and boundary values', () => {
      expect(getDataPrivacyGradeLabel(-1)).toBe(GRADE_VALUES.POOR);
      expect(getDataPrivacyGradeLabel(1.999999)).toBe(GRADE_VALUES.POOR);
      expect(getDataPrivacyGradeLabel(2.0)).toBe(GRADE_VALUES.MODERATE);
      expect(getDataPrivacyGradeLabel(4.0)).toBe(GRADE_VALUES.GOOD);
      expect(getDataPrivacyGradeLabel(6.0)).toBe(GRADE_VALUES.VERY_GOOD);
      expect(getDataPrivacyGradeLabel(8.0)).toBe(GRADE_VALUES.EXCELLENT);
    });
  });

  describe('getSyntheticQualityGradeLabel', () => {
    it('returns "Very Poor" for scores less than 2', () => {
      expect(getSyntheticQualityGradeLabel(0)).toBe(GRADE_VALUES.VERY_POOR);
      expect(getSyntheticQualityGradeLabel(1)).toBe(GRADE_VALUES.VERY_POOR);
      expect(getSyntheticQualityGradeLabel(1.99)).toBe(GRADE_VALUES.VERY_POOR);
    });

    it('returns "Poor" for scores between 2 and 3.99', () => {
      expect(getSyntheticQualityGradeLabel(2)).toBe(GRADE_VALUES.POOR);
      expect(getSyntheticQualityGradeLabel(3)).toBe(GRADE_VALUES.POOR);
      expect(getSyntheticQualityGradeLabel(3.99)).toBe(GRADE_VALUES.POOR);
    });

    it('returns "Moderate" for scores between 4 and 5.99', () => {
      expect(getSyntheticQualityGradeLabel(4)).toBe(GRADE_VALUES.MODERATE);
      expect(getSyntheticQualityGradeLabel(5)).toBe(GRADE_VALUES.MODERATE);
      expect(getSyntheticQualityGradeLabel(5.99)).toBe(GRADE_VALUES.MODERATE);
    });

    it('returns "Good" for scores between 6 and 7.99', () => {
      expect(getSyntheticQualityGradeLabel(6)).toBe(GRADE_VALUES.GOOD);
      expect(getSyntheticQualityGradeLabel(7)).toBe(GRADE_VALUES.GOOD);
      expect(getSyntheticQualityGradeLabel(7.99)).toBe(GRADE_VALUES.GOOD);
    });

    it('returns "Excellent" for scores 8 and above', () => {
      expect(getSyntheticQualityGradeLabel(8)).toBe(GRADE_VALUES.EXCELLENT);
      expect(getSyntheticQualityGradeLabel(9)).toBe(GRADE_VALUES.EXCELLENT);
      expect(getSyntheticQualityGradeLabel(10)).toBe(GRADE_VALUES.EXCELLENT);
      expect(getSyntheticQualityGradeLabel(100)).toBe(GRADE_VALUES.EXCELLENT);
    });

    it('handles edge cases and boundary values', () => {
      expect(getSyntheticQualityGradeLabel(-1)).toBe(GRADE_VALUES.VERY_POOR);
      expect(getSyntheticQualityGradeLabel(1.999999)).toBe(GRADE_VALUES.VERY_POOR);
      expect(getSyntheticQualityGradeLabel(2.0)).toBe(GRADE_VALUES.POOR);
      expect(getSyntheticQualityGradeLabel(4.0)).toBe(GRADE_VALUES.MODERATE);
      expect(getSyntheticQualityGradeLabel(6.0)).toBe(GRADE_VALUES.GOOD);
      expect(getSyntheticQualityGradeLabel(8.0)).toBe(GRADE_VALUES.EXCELLENT);
    });
  });

  describe('GRADE_ORDER', () => {
    it('contains all grade values in correct order', () => {
      expect(GRADE_ORDER).toEqual([
        GRADE_VALUES.UNAVAILABLE,
        GRADE_VALUES.VERY_POOR,
        GRADE_VALUES.POOR,
        GRADE_VALUES.MODERATE,
        GRADE_VALUES.GOOD,
        GRADE_VALUES.VERY_GOOD,
        GRADE_VALUES.EXCELLENT,
      ]);
    });

    it('has correct length', () => {
      expect(GRADE_ORDER).toHaveLength(7);
    });
  });

  describe('isPassingGrade', () => {
    it('returns true when grade equals reference grade', () => {
      expect(isPassingGrade(GRADE_VALUES.POOR, GRADE_VALUES.POOR)).toBe(true);
      expect(isPassingGrade(GRADE_VALUES.MODERATE, GRADE_VALUES.MODERATE)).toBe(true);
      expect(isPassingGrade(GRADE_VALUES.GOOD, GRADE_VALUES.GOOD)).toBe(true);
      expect(isPassingGrade(GRADE_VALUES.EXCELLENT, GRADE_VALUES.EXCELLENT)).toBe(true);
    });

    it('returns true when grade is higher than reference grade', () => {
      expect(isPassingGrade(GRADE_VALUES.POOR, GRADE_VALUES.MODERATE)).toBe(true);
      expect(isPassingGrade(GRADE_VALUES.POOR, GRADE_VALUES.EXCELLENT)).toBe(true);
      expect(isPassingGrade(GRADE_VALUES.MODERATE, GRADE_VALUES.GOOD)).toBe(true);
      expect(isPassingGrade(GRADE_VALUES.GOOD, GRADE_VALUES.EXCELLENT)).toBe(true);
      expect(isPassingGrade(GRADE_VALUES.VERY_POOR, GRADE_VALUES.VERY_GOOD)).toBe(true);
    });

    it('returns false when grade is lower than reference grade', () => {
      expect(isPassingGrade(GRADE_VALUES.EXCELLENT, GRADE_VALUES.GOOD)).toBe(false);
      expect(isPassingGrade(GRADE_VALUES.GOOD, GRADE_VALUES.MODERATE)).toBe(false);
      expect(isPassingGrade(GRADE_VALUES.MODERATE, GRADE_VALUES.POOR)).toBe(false);
      expect(isPassingGrade(GRADE_VALUES.POOR, GRADE_VALUES.VERY_POOR)).toBe(false);
      expect(isPassingGrade(GRADE_VALUES.VERY_GOOD, GRADE_VALUES.MODERATE)).toBe(false);
    });

    it('handles unavailable grade correctly', () => {
      expect(isPassingGrade(GRADE_VALUES.UNAVAILABLE, GRADE_VALUES.UNAVAILABLE)).toBe(true);
      expect(isPassingGrade(GRADE_VALUES.UNAVAILABLE, GRADE_VALUES.POOR)).toBe(true);
      expect(isPassingGrade(GRADE_VALUES.UNAVAILABLE, GRADE_VALUES.EXCELLENT)).toBe(true);
      expect(isPassingGrade(GRADE_VALUES.POOR, GRADE_VALUES.UNAVAILABLE)).toBe(false);
      expect(isPassingGrade(GRADE_VALUES.EXCELLENT, GRADE_VALUES.UNAVAILABLE)).toBe(false);
    });

    it('handles all combinations systematically', () => {
      const grades = [
        GRADE_VALUES.UNAVAILABLE,
        GRADE_VALUES.VERY_POOR,
        GRADE_VALUES.POOR,
        GRADE_VALUES.MODERATE,
        GRADE_VALUES.GOOD,
        GRADE_VALUES.VERY_GOOD,
        GRADE_VALUES.EXCELLENT,
      ];

      // Test all combinations
      for (let i = 0; i < grades.length; i++) {
        for (let j = 0; j < grades.length; j++) {
          const referenceGrade = grades[i];
          const grade = grades[j];
          const expected = i <= j; // passing if reference index <= grade index
          expect(isPassingGrade(referenceGrade, grade)).toBe(expected);
        }
      }
    });
  });
});
