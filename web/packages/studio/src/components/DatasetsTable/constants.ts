// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FilesetPurpose } from '@nemo/sdk/generated/platform/schema';

export const PURPOSE_LABELS: Record<FilesetPurpose, string> = {
  [FilesetPurpose.generic]: 'Generic',
  [FilesetPurpose.dataset]: 'Dataset',
  [FilesetPurpose.model]: 'Model',
};
