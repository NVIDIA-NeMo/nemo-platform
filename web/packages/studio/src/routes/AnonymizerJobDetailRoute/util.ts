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

export const parseJsonLines = <T>(content: string | undefined): T[] =>
  (content ?? '')
    .split('\n')
    .filter(Boolean)
    .flatMap((line) => {
      try {
        return [JSON.parse(line) as T];
      } catch {
        return [];
      }
    });

/** Rewrite writes `<column>_rewritten`; the replace strategies write `<column>_replaced`. */
const OUTPUT_SUFFIXES = ['_rewritten', '_replaced'];

/**
 * Source column first, then its anonymized counterpart, then whatever else the run produced.
 * Matching the suffix exactly matters — replace runs also emit `<column>_with_spans`.
 */
export const orderResultColumns = (columns: string[], textColumn: string | undefined): string[] => {
  if (!textColumn || !columns.includes(textColumn)) return columns;
  const output = OUTPUT_SUFFIXES.map((suffix) => `${textColumn}${suffix}`).find((column) =>
    columns.includes(column)
  );
  const lead = output ? [textColumn, output] : [textColumn];
  return [...lead, ...columns.filter((column) => !lead.includes(column))];
};
