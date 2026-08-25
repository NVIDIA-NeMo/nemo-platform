// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { isMappingDraftDirty } from '@studio/components/transform/draft';
import {
  CUSTOM_FORMAT_ID,
  findOutputFormat,
  OUTPUT_FORMATS,
  type OutputFormat,
} from '@studio/components/transform/formats';
import {
  autoMapFields,
  buildTemplate,
  columnReference,
  missingRequiredPaths,
  resolveGeneratedIdColumn,
  usesGeneratedIdColumn,
  type CustomTemplateRow,
} from '@studio/components/transform/template';
import { useCallback, useEffect, useMemo, useState } from 'react';

const BLANK_ROW: CustomTemplateRow = { key: '', value: '' };

export interface TransformMapping {
  format: OutputFormat;
  isCustom: boolean;
  setFormat: (id: string) => void;
  mappings: Record<string, string>;
  setMapping: (path: string, value: string) => void;
  rawPaths: ReadonlySet<string>;
  toggleRaw: (path: string) => void;
  customRows: CustomTemplateRow[];
  setCustomRows: (rows: CustomTemplateRow[]) => void;
  /** Source columns the mapping was built against. */
  columns: readonly string[];
  /** The finished `schema_transform` template. */
  template: Record<string, unknown>;
  missingRequired: string[];
  generatedIdColumn: string;
  /** Whether the template still references the generated identifier column. */
  needsGeneratedId: boolean;
  /** No required field is unmapped and the template writes at least one key. */
  isComplete: boolean;
  /** Whether the mapping holds work the user would lose by closing. */
  isDirty: boolean;
}

interface Options {
  /** Column names of the source file, as read from its first row. */
  columns: readonly string[];
  /** Called when the user picks a different target format, for dependent defaults. */
  onFormatChange?: (format: OutputFormat) => void;
}

/**
 * The custom grid starts as a passthrough of the source columns, so renaming or
 * dropping a couple of fields is an edit rather than a from-scratch schema. The
 * trailing blank row is what `CustomTemplateRows` appends to.
 */
const baselineCustomRows = (isCustom: boolean, columns: readonly string[]): CustomTemplateRow[] =>
  isCustom
    ? [...columns.map((column) => ({ key: column, value: columnReference(column) })), BLANK_ROW]
    : [BLANK_ROW];

/**
 * Owns the field mapping shared by every transform surface: the chosen output
 * format, the per-field templates, and the custom key/template grid. The
 * mapping is re-guessed from the source columns whenever either changes, so a
 * caller only has to supply the columns.
 */
export const useTransformMapping = ({ columns, onFormatChange }: Options): TransformMapping => {
  const [formatId, setFormatId] = useState(OUTPUT_FORMATS[0].id);
  const [mappings, setMappings] = useState<Record<string, string>>({});
  const [rawPaths, setRawPaths] = useState<ReadonlySet<string>>(new Set());
  const [customRows, setCustomRows] = useState<CustomTemplateRow[]>([BLANK_ROW]);

  const format = findOutputFormat(formatId) ?? OUTPUT_FORMATS[0];
  const isCustom = format.id === CUSTOM_FORMAT_ID;
  const generatedIdColumn = useMemo(() => resolveGeneratedIdColumn(columns), [columns]);

  // Re-guess the mapping whenever the target format or the source columns change.
  const columnsKey = columns.join(',');
  useEffect(() => {
    setMappings(autoMapFields(format, columns, generatedIdColumn));
    setRawPaths(new Set());
    setCustomRows(baselineCustomRows(format.id === CUSTOM_FORMAT_ID, columns));
    // `columnsKey` stands in for `columns`, which is a new array on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [format, columnsKey]);

  const setFormat = useCallback(
    (id: string) => {
      const next = findOutputFormat(id);
      if (!next) {
        return;
      }
      setFormatId(next.id);
      onFormatChange?.(next);
    },
    [onFormatChange]
  );

  const setMapping = useCallback((path: string, value: string) => {
    setMappings((prev) => ({ ...prev, [path]: value }));
  }, []);

  const toggleRaw = useCallback((path: string) => {
    setRawPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }, []);

  const template = useMemo(
    () => buildTemplate(format, mappings, isCustom ? customRows : []),
    [format, mappings, isCustom, customRows]
  );
  const missingRequired = useMemo(
    () => (isCustom ? [] : missingRequiredPaths(format, mappings)),
    [isCustom, format, mappings]
  );

  const isDirty = useMemo(
    () =>
      isMappingDraftDirty(
        { mappings, rawPaths, customRows },
        {
          mappings: autoMapFields(format, columns, generatedIdColumn),
          customRows: baselineCustomRows(format.id === CUSTOM_FORMAT_ID, columns),
        }
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [mappings, rawPaths, customRows, format, columnsKey, generatedIdColumn]
  );

  return {
    format,
    isCustom,
    setFormat,
    mappings,
    setMapping,
    rawPaths,
    toggleRaw,
    customRows,
    setCustomRows,
    columns,
    template,
    missingRequired,
    generatedIdColumn,
    // Only true while the finished template still references it, so clearing or
    // overwriting the id field also drops the column from the job.
    needsGeneratedId: usesGeneratedIdColumn(template, generatedIdColumn, columns),
    isComplete: missingRequired.length === 0 && Object.keys(template).length > 0,
    isDirty,
  };
};
