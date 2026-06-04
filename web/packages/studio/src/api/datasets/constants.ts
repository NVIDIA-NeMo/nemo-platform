// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export const ALLOWED_CONTENT_FILE_TYPES = new Set(['csv', 'json', 'jsonl', 'parquet']); // File types that the platform parses as structured data.

// Fast-path blocklist for extensions that are unambiguously binary. Files
// matching these are rejected immediately without a HEAD request. Unknown
// extensions fall through to Content-Type detection (see useIsBinaryFile).
// Keep this list short — it's a hint, not an authoritative registry.
export const BINARY_FILE_EXTENSIONS = new Set([
  // Images
  'png',
  'jpg',
  'jpeg',
  'gif',
  'webp',
  'ico',
  // Archives
  'zip',
  'tar',
  'gz',
  // ML weights / binary data
  'pt',
  'pth',
  'safetensors',
  'pkl',
  'bin',
  'npy',
  'npz',
  'h5',
  // Documents
  'pdf',
]);

export const COMPLETION_PROMPT_KEY_ORDER = ['prompt', 'instruction', 'question']; // Searches for a prompt in the following keys
