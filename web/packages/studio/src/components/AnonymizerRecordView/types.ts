// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export interface AnonymizerEntity {
  readonly value: string;
  readonly label: string;
  readonly start: number;
  readonly end: number;
}

export interface EntityReplacement {
  readonly original: string;
  readonly label: string;
  readonly synthetic: string;
}

export interface TextSegment {
  readonly text: string;
  readonly label?: string;
}

export interface AnonymizerRecord {
  readonly original: string;
  readonly replaced: string;
  readonly originalSegments: readonly TextSegment[];
  readonly replacedSegments: readonly TextSegment[];
  readonly replacements: readonly EntityReplacement[];
}
