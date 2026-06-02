// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FilesetFileOutput, FilesetOutput } from '@nemo/sdk/generated/platform/schema';
import YAML from 'yaml';

export interface ParsedReadme {
  content: string;
  metadata?: Record<string, unknown>;
}

export const isRootReadme = (file: FilesetFileOutput): boolean => {
  if (file.path.includes('/')) return false;
  const lower = file.path.toLowerCase();
  return lower === 'readme.md' || lower === 'readme.markdown';
};

export const parseReadme = (content: string): ParsedReadme => {
  const normalized = content.charCodeAt(0) === 0xfeff ? content.slice(1) : content;

  if (!normalized.startsWith('---')) {
    return { content: normalized };
  }

  const frontMatterEndIndex = normalized.indexOf('\n---', 3);
  if (frontMatterEndIndex === -1) {
    return { content: normalized };
  }

  const frontMatter = normalized.slice(3, frontMatterEndIndex).trim();
  const sliceStart = frontMatterEndIndex + 4;
  const bodyStartIndex = normalized.indexOf('\n', sliceStart);
  const start = bodyStartIndex === -1 ? sliceStart : bodyStartIndex + 1;
  const body = normalized.slice(start).trimStart();

  try {
    const parsed = YAML.parse(frontMatter);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return { content: body, metadata: parsed as Record<string, unknown> };
    }
  } catch {
    return { content: normalized };
  }

  return { content: body };
};

export interface ModelSource {
  path: string;
  creatorSlug: string;
}

export const getModelSource = (fileset: FilesetOutput): ModelSource | undefined => {
  const { storage } = fileset;

  if (storage.type === 'huggingface' && 'repo_id' in storage && storage.repo_id) {
    const [creator] = storage.repo_id.split('/');
    if (!creator) return undefined;
    return { path: storage.repo_id, creatorSlug: normalizeCreatorSlug(creator) };
  }

  if (
    storage.type === 'ngc' &&
    'org' in storage &&
    storage.org &&
    'target' in storage &&
    storage.target
  ) {
    const path = storage.team
      ? `${storage.org}/${storage.team}/${storage.target}`
      : `${storage.org}/${storage.target}`;
    return {
      path,
      creatorSlug: normalizeCreatorSlug(storage.org),
    };
  }

  if (fileset.workspace && fileset.name) {
    return {
      path: `${fileset.workspace}/${fileset.name}`,
      creatorSlug: normalizeCreatorSlug(fileset.workspace),
    };
  }

  return undefined;
};

const normalizeCreatorSlug = (raw: string): string => {
  const lower = raw.toLowerCase();
  return lower.split('-')[0] ?? lower;
};
