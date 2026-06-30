// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FileFormat, type FileFormatType } from '@nemo/common/src/types';

export const INFER_FROM_EXISTING_MAX_FILES = 10;

export const FORMAT_BY_EXTENSION: Record<string, FileFormatType> = {
  json: FileFormat.JSON,
  jsonl: FileFormat.JSONL,
  csv: FileFormat.CSV,
  parquet: FileFormat.PARQUET,
};
