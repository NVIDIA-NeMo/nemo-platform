// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getColumnWidth } from '@nemo/common/src/components/DataView/internal/hooks/useResizableColumns';

/** The custom property named by a `calc(var(…) * 1px)` width. */
const referencedProperty = (width: string): string => {
  const match = /var\((?<name>.*?)\)/.exec(width);
  if (!match?.groups) throw new Error(`no var() reference in "${width}"`);
  return match.groups.name;
};

/** Whether a custom property name parses as CSS: every character has to be one an identifier
 * allows, or be backslash-escaped. jsdom's style parser rejects `calc(var(…))` whatever the name,
 * so validity is asserted on the name itself rather than by assigning it to an element. */
const isValidCustomPropertyName = (name: string): boolean => /^--(?:[\w-]|\\[^\w\s])+$/.test(name);

/** Resolve escapes the way the CSS parser does, giving the property name the reference lands on. */
const resolveEscapes = (name: string): string => name.replace(/\\(.)/g, '$1');

/** Column ids as the data views actually build them. The dotted ones are what broke: an evaluator
 * column is named for its metric, and a run column can carry a `/` or `:` from a model ref. */
const COLUMN_IDS = [
  'created_at',
  'metadata-eval_config_fileset',
  'evaluator-llm-judge.answers_question',
  'evaluator-string-check.string-check',
  'run-0-default/claude-haiku-4-5:20251001',
];

describe('getColumnWidth', () => {
  it('reads the column size custom property', () => {
    expect(getColumnWidth('created_at')).toBe('calc(var(--col-created_at-size) * 1px)');
  });

  it('escapes characters an identifier does not allow', () => {
    expect(getColumnWidth('evaluator-llm-judge.answers_question')).toBe(
      'calc(var(--col-evaluator-llm-judge\\.answers_question-size) * 1px)'
    );
  });

  it.each(COLUMN_IDS)('names a property the CSS parser can read for %s', (id) => {
    // An unparseable name invalidates the whole declaration, so the cell loses its width and sizes
    // to its own content instead — which is what pushed headers off the columns they label.
    expect(isValidCustomPropertyName(referencedProperty(getColumnWidth(id)))).toBe(true);
  });

  it.each(COLUMN_IDS)('resolves to the property declared for %s', (id) => {
    // `getColumnWidths` declares `--col-<raw id>-size` through the CSSOM, which takes the name
    // literally. The escaped reference has to land back on exactly that name to find the width.
    expect(resolveEscapes(referencedProperty(getColumnWidth(id)))).toBe(`--col-${id}-size`);
  });
});
