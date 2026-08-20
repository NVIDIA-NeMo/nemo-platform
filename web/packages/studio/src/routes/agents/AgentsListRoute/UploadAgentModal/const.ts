// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { UploadAgentEntry } from '@studio/routes/agents/AgentsListRoute/UploadAgentModal/type';
import YAML from 'yaml';
import { z } from 'zod';

export const AGENT_CONFIG_FILENAME = 'agent.yaml';

export const FABRIC_CONFIG_FORMAT = 'nemo-agents-spec-v1';

// Container staging skips this file, so its bytes never reach a deployment.
const AGENT_SPEC_FILENAME = 'AGENT-SPEC.md';

// Mirrors MAX_AGENT_SPEC_STAGED_BYTES / _FILES; the platform only enforces them at deploy.
export const MAX_AGENT_SPEC_BYTES = 900_000;
export const MAX_AGENT_SPEC_FILES = 500;

// A directory picker hands over every descendant, so a mistaken pick can arrive with
// hundreds of thousands of entries. Reject on the raw count before mapping, filtering or
// sorting any of them — the ignore list cannot be applied without touching every entry.
export const MAX_PICKED_FILES = 1_000;

export const tooManyPickedFiles = (pickedCount: number): string | undefined =>
  pickedCount > MAX_PICKED_FILES
    ? `That directory holds ${pickedCount.toLocaleString()} files, far more than an agent directory should. Point at the agent's own directory.`
    : undefined;

const IGNORED_DIRECTORIES = new Set([
  '__pycache__',
  '.git',
  '.venv',
  'venv',
  'node_modules',
  '.mypy_cache',
  '.pytest_cache',
  '.ruff_cache',
  '.idea',
  '.vscode',
]);

const IGNORED_FILENAMES = new Set(['.DS_Store', 'Thumbs.db']);

const IGNORED_EXTENSIONS = ['.pyc', '.pyo', '.pyd', '.so', '.dylib', '.dll'];

export const uploadAgentFormSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, 'Name is required')
    .regex(/^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/, 'Use lowercase letters, numbers, and hyphens'),
});

/** Convention only — the Agent entity stores no reference to it. */
export const agentSpecFilesetName = (agentName: string): string => `${agentName}-spec`;

export const isIgnoredPath = (path: string): boolean => {
  const segments = path.split('/');
  if (segments.some((segment) => IGNORED_DIRECTORIES.has(segment))) return true;

  const filename = segments[segments.length - 1] ?? '';
  if (IGNORED_FILENAMES.has(filename)) return true;

  return IGNORED_EXTENSIONS.some((extension) => filename.endsWith(extension));
};

/** The fileset holds the directory's contents, so the picked root is stripped from each path. */
export const collectAgentEntries = (files: File[]): UploadAgentEntry[] => {
  const entries: UploadAgentEntry[] = [];

  for (const file of files) {
    const relativePath = file.webkitRelativePath || file.name;
    const path = relativePath.split('/').slice(1).join('/') || file.name;
    if (!path || isIgnoredPath(path)) continue;
    entries.push({ path, file });
  }

  return entries.sort((left, right) => left.path.localeCompare(right.path));
};

export const totalEntryBytes = (entries: UploadAgentEntry[]): number =>
  entries.reduce((total, entry) => total + entry.file.size, 0);

export const validateAgentEntries = (entries: UploadAgentEntry[]): string | undefined => {
  if (entries.length === 0) return 'That directory has no uploadable files.';

  if (!entries.some((entry) => entry.path === AGENT_CONFIG_FILENAME)) {
    return `No ${AGENT_CONFIG_FILENAME} at the top level of that directory.`;
  }

  if (entries.length > MAX_AGENT_SPEC_FILES) {
    return `That directory holds ${entries.length} files; the limit is ${MAX_AGENT_SPEC_FILES}. Point at a directory containing only the agent's own files.`;
  }

  const bytes = totalEntryBytes(entries);
  if (bytes > MAX_AGENT_SPEC_BYTES) {
    return `That directory is ${Math.round(bytes / 1000)} KB; the limit is ${Math.round(MAX_AGENT_SPEC_BYTES / 1000)} KB. Point at a directory containing only the agent's own files.`;
  }

  return undefined;
};

// Container deployments read every staged file as text and fail on a decode error.
export const findNonUtf8Path = async (entries: UploadAgentEntry[]): Promise<string | undefined> => {
  const decoder = new TextDecoder('utf-8', { fatal: true });

  for (const entry of entries) {
    if (entry.path.split('/').pop() === AGENT_SPEC_FILENAME) continue;
    try {
      decoder.decode(await entry.file.arrayBuffer());
    } catch {
      return entry.path;
    }
  }

  return undefined;
};

export class AgentConfigParseError extends Error {}

export const parseAgentConfig = (text: string): Record<string, unknown> => {
  let parsed: unknown;
  try {
    parsed = YAML.parse(text);
  } catch (error) {
    throw new AgentConfigParseError(
      `${AGENT_CONFIG_FILENAME} is not valid YAML: ${(error as Error).message}`
    );
  }

  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    throw new AgentConfigParseError(`${AGENT_CONFIG_FILENAME} must contain a YAML mapping.`);
  }

  const config = parsed as Record<string, unknown>;
  const configFormat = config.config_format;
  if (configFormat !== FABRIC_CONFIG_FORMAT) {
    throw new AgentConfigParseError(
      `${AGENT_CONFIG_FILENAME} must set config_format: ${FABRIC_CONFIG_FORMAT}${
        typeof configFormat === 'string' ? ` (found ${configFormat})` : ''
      }.`
    );
  }

  return config;
};

export const agentNameFromConfig = (config: Record<string, unknown>): string | undefined =>
  typeof config.name === 'string' && config.name.trim() ? config.name.trim() : undefined;
