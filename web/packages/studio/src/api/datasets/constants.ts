// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export const ALLOWED_CONTENT_FILE_TYPES = new Set(['csv', 'json', 'jsonl', 'parquet']); // File types that the platform parses as structured data.

// Extensions that are known binary formats. We skip the download and show a
// "preview not available" message instead — downloading and rendering binary
// content as text is both slow and meaningless.
// Everything NOT in this set is treated as text and rendered in the plain-text
// editor (the old allowlist was too restrictive; .gitattributes, .py, YAML,
// shell scripts, etc. are all valid text previews).
export const BINARY_FILE_EXTENSIONS = new Set([
  // Images
  'png',
  'jpg',
  'jpeg',
  'gif',
  'bmp',
  'webp',
  'ico',
  'svg',
  'tiff',
  'tif',
  // Archives
  'zip',
  'tar',
  'gz',
  'bz2',
  'xz',
  'zst',
  '7z',
  'rar',
  // ML model / weight formats
  'bin',
  'pt',
  'pth',
  'ckpt',
  'safetensors',
  'pkl',
  'pickle',
  'onnx',
  'pb',
  // Other binary
  'pdf',
  'arrow',
  'npy',
  'npz',
  'h5',
  'hdf5',
  'db',
  'sqlite',
  'wasm',
  'dll',
  'so',
  'dylib',
  'exe',
]);

export const COMPLETION_PROMPT_KEY_ORDER = ['prompt', 'instruction', 'question']; // Searches for a prompt in the following keys
