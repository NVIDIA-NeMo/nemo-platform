// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * External filesets (HuggingFace, NGC, mirrored S3) routinely contain many
 * non-data files: README.md, LICENSE, images, scripts, model artifacts. None
 * of those carry a JSON Schema, so the dataset detail UI uses this predicate
 * to skip them in the Schema column, in the "Schema will be applied to N
 * files" count, and anywhere else we iterate `filesList` for schema purposes.
 *
 * The naive heuristic covers what the inference pipeline supports today
 * (`.json` / `.jsonl` / `.csv` / `.parquet`).
 */

const SCHEMA_ASSIGNABLE_EXTENSIONS = new Set(['json', 'jsonl', 'csv', 'parquet']);

export function isSchemaAssignableFile(path: string): boolean {
  const ext = path.split('.').pop()?.toLowerCase();
  return ext !== undefined && SCHEMA_ASSIGNABLE_EXTENSIONS.has(ext);
}
