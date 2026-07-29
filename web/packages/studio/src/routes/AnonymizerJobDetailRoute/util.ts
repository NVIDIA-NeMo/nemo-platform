// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RunJob } from '@nemo/sdk/generated/anonymizer/schema';

export const ANONYMIZER_POLLING_INTERVAL_MS = 5000;

export const jobStrategy = (job: RunJob): string | undefined => {
  const config = job.spec?.request?.config;
  if (!config) return undefined;
  if (config.rewrite) return 'rewrite';
  return (config.replace as { kind?: string } | undefined)?.kind;
};

export const jobSource = (job: RunJob): string | undefined => job.spec?.request?.data?.source;

export const RESULT_PREVIEW_ROWS = 20;

export interface ArtifactLocation {
  readonly fileset: string;
  readonly basePath: string;
}

/** `default/job-fileset-x#results/attempt-1/artifacts` → fileset `job-fileset-x`, path `results/…`. */
export const parseArtifactUrl = (artifactUrl: string | undefined): ArtifactLocation | undefined => {
  const [reference, basePath] = artifactUrl?.split('#') ?? [];
  if (!reference || !basePath) return undefined;
  const fileset = reference.split('/').pop();
  return fileset ? { fileset, basePath } : undefined;
};

export const metadataTextColumn = (metadata: string | undefined): string | undefined => {
  try {
    return (JSON.parse(metadata ?? '{}') as { original_text_column?: string }).original_text_column;
  } catch {
    return undefined;
  }
};

/** Rewrite writes `<column>_rewritten`; the replace strategies write `<column>_replaced`. */
const OUTPUT_SUFFIXES = ['_rewritten', '_replaced'];

export const orderResultColumns = (columns: string[], textColumn: string | undefined): string[] => {
  if (!textColumn || !columns.includes(textColumn)) return columns;
  const output = OUTPUT_SUFFIXES.map((suffix) => `${textColumn}${suffix}`).find((column) =>
    columns.includes(column)
  );
  const lead = output ? [textColumn, output] : [textColumn];
  return [...lead, ...columns.filter((column) => !lead.includes(column))];
};
