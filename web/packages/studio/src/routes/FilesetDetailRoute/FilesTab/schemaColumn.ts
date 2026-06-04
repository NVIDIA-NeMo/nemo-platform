// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { isSchemaAssignableFile } from '@nemo/common/src/utils/jsonSchema';
import type { DatasetMetadataContent } from '@nemo/sdk/generated/platform/schema';

/**
 * Resolve the Schema-column label for one file row.
 *
 *   `.json` / `.jsonl` only — non-data files (README, images, scripts) return
 *   null because they cannot carry a schema even when one is set.
 *
 *   Mapping precedence:
 *     1. `schemas_by_path[path]` is a string ref      -> show that key
 *     2. `schemas_by_path[path]` is an inline object  -> "(inline)"
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
  // Inline objects in schemas_by_path are only produced by hand-editing the
  // raw JSON via the advanced "Show All" view — not by normal inference/save
  // flows. No useful label to show; fall through to the root-schema default.
  if (mapped && typeof mapped === 'object') return null;
  const rootSchema = metadata?.schema;
  if (typeof rootSchema === 'string') return rootSchema;
  if (rootSchema !== undefined && rootSchema !== null) return 'default';
  return null;
}
