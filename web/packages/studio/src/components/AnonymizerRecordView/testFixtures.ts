// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type {
  AnonymizerEntity,
  EntityReplacement,
} from '@studio/components/AnonymizerRecordView/types';

export const ORIGINAL = 'Bobby, a 40-year-old veterinarian.';
export const REPLACED = 'Teddy, a 45-year-old veterinarian.';

/** The parsed shape. Kept literal so `parseEntities` is asserted against data, not a second mapping. */
export const entities: AnonymizerEntity[] = [
  { value: 'Bobby', label: 'first_name', start: 0, end: 5 },
  { value: '40', label: 'age', start: 9, end: 11 },
];

export const replacements: EntityReplacement[] = [
  { original: 'Bobby', label: 'first_name', synthetic: 'Teddy' },
  { original: '40', label: 'age', synthetic: '45' },
];

export const traceRow = {
  biography: ORIGINAL,
  biography_replaced: REPLACED,
  final_entities: {
    entities: [
      { value: 'Bobby', label: 'first_name', start_position: 0, end_position: 5 },
      { value: '40', label: 'age', start_position: 9, end_position: 11 },
    ],
  },
  _replacement_map: { replacements },
};
