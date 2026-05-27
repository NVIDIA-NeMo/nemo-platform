// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export const GRADE_VALUES = {
  VERY_POOR: 'Very Poor',
  POOR: 'Poor',
  MODERATE: 'Moderate',
  GOOD: 'Good',
  VERY_GOOD: 'Very Good',
  EXCELLENT: 'Excellent',
  UNAVAILABLE: 'Unavailable',
};

export function getDataPrivacyGradeLabel(score: number): string {
  if (Number.isNaN(score)) return GRADE_VALUES.UNAVAILABLE;
  if (score < 2) return GRADE_VALUES.POOR;
  if (score < 4) return GRADE_VALUES.MODERATE;
  if (score < 6) return GRADE_VALUES.GOOD;
  if (score < 8) return GRADE_VALUES.VERY_GOOD;
  return GRADE_VALUES.EXCELLENT;
}

export function getSyntheticQualityGradeLabel(score: number): string {
  if (Number.isNaN(score)) return GRADE_VALUES.UNAVAILABLE;
  if (score < 2) return GRADE_VALUES.VERY_POOR;
  if (score < 4) return GRADE_VALUES.POOR;
  if (score < 6) return GRADE_VALUES.MODERATE;
  if (score < 8) return GRADE_VALUES.GOOD;
  return GRADE_VALUES.EXCELLENT;
}

export const GRADE_ORDER = [
  GRADE_VALUES.UNAVAILABLE,
  GRADE_VALUES.VERY_POOR,
  GRADE_VALUES.POOR,
  GRADE_VALUES.MODERATE,
  GRADE_VALUES.GOOD,
  GRADE_VALUES.VERY_GOOD,
  GRADE_VALUES.EXCELLENT,
];

export const isPassingGrade = (referenceGrade: string, grade: string) => {
  return GRADE_ORDER.indexOf(referenceGrade) <= GRADE_ORDER.indexOf(grade);
};
