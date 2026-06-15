// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { isSchemaAssignableFile } from '@nemo/common/src/utils/jsonSchema';
import type { DatasetMetadataContent } from '@nemo/sdk/generated/platform/schema';

/**
 * Resolve the Schema-column label for one file row.
 *
 *   `.json` / `.jsonl` / `.csv` / `.parquet` only — non-data files (README, images, scripts) return
 *   null because they cannot carry a schema even when one is set.
 *
 *   Mapping precedence:
 *     1. `schemas_by_path[path]` is a string ref      -> show that key
 *     2. `schemas_by_path[path]` is an inline object  -> null (no label)
 *     3. No per-file mapping + root schema is a ref   -> show that key
 *     4. No per-file mapping + root schema is inline  -> "default"
 *     5. Otherwise                                    -> null (blank cell)
 */
export function getSchemaCellLabel(
  filePath: string,
  metadata: DatasetMetadataContent | undefined
): string | null {
  if (!isSchemaAssignableFile(filePath)) return null;
  const mapped = metadata?.schemas_by_path?.[filePath];
  if (typeof mapped === 'string') return mapped;
  // Inline objects in schemas_by_path have no $ref key to display — they are
  // anonymous, hand-crafted schemas from the "Show All" JSON editor. Return
  // null (blank cell) because there is no meaningful label to show.
  if (mapped && typeof mapped === 'object') return null;
  const rootSchema = metadata?.schema;
  if (typeof rootSchema === 'string') return rootSchema;
  if (rootSchema !== undefined && rootSchema !== null) return 'default';
  return null;
}
