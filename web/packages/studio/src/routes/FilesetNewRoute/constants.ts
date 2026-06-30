// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FilesetPurpose } from '@nemo/sdk/generated/platform/schema';

export const DATASET_NAME_REQUIRED_MESSAGE = 'Name is required.';

export const DATASET_NAME_PATTERN_MESSAGE =
  'Name must start with a lowercase letter, be 2–63 characters, and contain only lowercase letters, digits, hyphens, dots, underscores, plus, and @ (no consecutive hyphens, cannot end with a hyphen).';

/** Per-purpose copy shown in the purpose selector. Kept adjacent to the enum so each value has user-facing explanation. */
export const PURPOSE_OPTIONS: {
  value: FilesetPurpose;
  label: string;
  description: string;
}[] = [
  {
    value: FilesetPurpose.generic,
    label: 'Generic',
    description:
      "Default. Use for files that don't fit the Dataset or Model categories. Doesn't add purpose-specific metadata fields.",
  },
  {
    value: FilesetPurpose.dataset,
    label: 'Dataset',
    description:
      'For training and evaluation data. Enables dataset-specific metadata, including schema information.',
  },
  {
    value: FilesetPurpose.model,
    label: 'Model',
    description:
      'For model weights and checkpoints. Enables model-specific metadata, including tool-calling and model configuration fields.',
  },
];

export const DATASET_TYPE_CUSTOM = 'custom';
export const DATASET_TYPE_SAMPLE = 'sample';
