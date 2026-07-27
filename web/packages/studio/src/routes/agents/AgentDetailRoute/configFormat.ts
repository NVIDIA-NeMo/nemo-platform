// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

const ACRONYMS: Record<string, string> = {
  llm: 'LLM',
  llms: 'LLMs',
  url: 'URL',
  api: 'API',
  id: 'ID',
  uri: 'URI',
};

/** Turns a snake_case / camelCase config key into a readable label. */
export const humanizeKey = (key: string): string =>
  key
    .replace(/([a-z\d])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .trim()
    .split(' ')
    .filter(Boolean)
    .map((word) => ACRONYMS[word.toLowerCase()] ?? word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
