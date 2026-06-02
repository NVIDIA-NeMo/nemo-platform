// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { MultiselectOption } from '@studio/constants/mutliselect';

export const LOADING_FILES_OPTION: MultiselectOption = {
  label: 'Loading files...',
  value: 'loading',
  isDisabled: true,
};

export enum FeedbackAddToDatasetFileSource {
  New = 'Create new',
  Existing = 'Add to existing',
}
