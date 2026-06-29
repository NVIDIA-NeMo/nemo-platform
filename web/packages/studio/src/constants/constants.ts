/*
 * SPDX-FileCopyrightText: Copyright (c) 2022-2023 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */

export const CHAT_DEFAULT_MAX_TOKENS = 4096;
export const DEFAULT_LARGE_PAGE_SIZE = 1000;
export const DATASET_NAME_REGEX = /^[a-zA-Z0-9._-]+$/;
export const DEFAULT_MODEL_NAME = 'meta/llama-3.1-8b-instruct';
export const DEFAULT_NAMESPACE = 'default';
export const DEFAULT_API_ERR_MSG = 'Invalid API response. Please try again later.';
export const DEFAULT_TOOLS_FILE_NAME = 'tools.json';
export const EMPTY_FIELD_VALUE = '-';
export const EMPTY_FIELD_EMDASH_VALUE = '—';
export const DEFAULT_BUILD_MODEL_NAME = 'nvidia-llama-3-3-nemotron-super-49b-v1';

export const KNOWN_TEXT_EXTENSIONS = new Set([
  // Data
  'json',
  'jsonl',
  'csv',
  'tsv',
  // Code
  'py',
  'js',
  'jsx',
  'ts',
  'tsx',
  'java',
  'c',
  'cpp',
  'h',
  'go',
  'rs',
  'rb',
  'php',
  'swift',
  'kt',
  'scala',
  'r',
  'm',
  'sh',
  'bash',
  'zsh',
  'fish',
  // Markup / Config
  'html',
  'htm',
  'xml',
  'yaml',
  'yml',
  'toml',
  'ini',
  'cfg',
  'conf',
  'jsonc',
  'env',
  // Text
  'txt',
  'md',
  'rst',
  'log',
  'diff',
  'patch',
  // Other
  'sql',
  'graphql',
  'proto',
  'dockerfile',
  'makefile',
]);
