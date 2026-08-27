// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { CustomTemplateRow } from '@studio/components/transform/template';

/** The editable mapping state shared by every transform surface. */
export interface MappingDraft {
  readonly mappings: Readonly<Record<string, string>>;
  /** Fields switched from the column picker to a raw template input. */
  readonly rawPaths: ReadonlySet<string>;
  readonly customRows: readonly CustomTemplateRow[];
}

/** What the mapping would hold with no user input, for the current format and file. */
export interface MappingBaseline {
  readonly mappings: Readonly<Record<string, string>>;
  readonly customRows: readonly CustomTemplateRow[];
}

/** Turns a name into the slug used for generated job names. */
export const slugify = (value: string): string =>
  value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');

/** Blank and absent mean the same thing for a mapping, so both normalize away. */
const withoutBlanks = (mappings: Readonly<Record<string, string>>): Record<string, string> =>
  Object.fromEntries(Object.entries(mappings).filter(([, value]) => value.trim() !== ''));

const sameMappings = (
  a: Readonly<Record<string, string>>,
  b: Readonly<Record<string, string>>
): boolean => {
  const left = withoutBlanks(a);
  const right = withoutBlanks(b);
  const keys = Object.keys(left);
  return keys.length === Object.keys(right).length && keys.every((key) => left[key] === right[key]);
};

/** Trailing blank rows are an editing affordance, not content. */
const filledRows = (rows: readonly CustomTemplateRow[]): CustomTemplateRow[] =>
  rows.filter((row) => row.key.trim() !== '' || row.value.trim() !== '');

const sameCustomRows = (
  a: readonly CustomTemplateRow[],
  b: readonly CustomTemplateRow[]
): boolean => {
  const left = filledRows(a);
  const right = filledRows(b);
  return (
    left.length === right.length &&
    left.every(
      (row, index) =>
        row.key.trim() === right[index].key.trim() && row.value.trim() === right[index].value.trim()
    )
  );
};

/**
 * Whether the mapping holds work the user would lose by closing.
 *
 * Compared against the baseline rather than tracked as an "edited" flag, so
 * merely switching target format — which re-derives every default — does not
 * count, and neither does typing a value back to what it already was.
 */
export const isMappingDraftDirty = (draft: MappingDraft, baseline: MappingBaseline): boolean =>
  !sameMappings(draft.mappings, baseline.mappings) ||
  draft.rawPaths.size > 0 ||
  !sameCustomRows(draft.customRows, baseline.customRows);
