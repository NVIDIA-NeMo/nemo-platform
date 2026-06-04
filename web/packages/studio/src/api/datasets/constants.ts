// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export const ALLOWED_CONTENT_FILE_TYPES = new Set(['csv', 'json', 'jsonl', 'parquet']); // File types that the platform parses as structured data.

// File types that Studio's FileContentPreview can render. Superset of ALLOWED_CONTENT_FILE_TYPES:
// includes formats we can display but do not structurally manipulate.
export const PREVIEWABLE_FILE_TYPES = new Set([
  ...ALLOWED_CONTENT_FILE_TYPES,
  'md',
  'markdown',
  'txt',
]);

export const COMPLETION_PROMPT_KEY_ORDER = ['prompt', 'instruction', 'question']; // Searches for a prompt in the following keys
