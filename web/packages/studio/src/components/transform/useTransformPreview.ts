// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { renderTemplate } from '@studio/components/transform/renderTemplate';
import { parseFileContent, type Row } from '@studio/util/files';
import { useMemo, useState } from 'react';

interface Props {
  fileContent: string | undefined;
  fileType: string;
  /** The `schema_transform` template applied to the previewed row. */
  template: Record<string, unknown>;
  /**
   * Column the transform generates rather than reads. The preview stands in a
   * placeholder for it so a generated identifier does not render as empty.
   */
  generatedIdColumn?: string;
}

export interface UseTransformPreviewResult {
  /** 1-based index of the row actually shown. */
  currentRow: number;
  totalRows: number;
  sourceRow: Row | null;
  afterRow: Row | null;
  /** True when the rendered row could not be produced faithfully in the browser. */
  approximated: boolean;
  onRowChange: (row: number) => void;
}

/** Stable stand-in for a generated identifier, so the preview does not churn. */
const placeholderId = (index: number): string =>
  ((index + 1) * 2654435761).toString(16).slice(-8).padStart(8, '0');

/**
 * Renders one source row through the current template so the mapping can be
 * checked against real data before anything is written.
 */
export const useTransformPreview = ({
  fileContent,
  fileType,
  template,
  generatedIdColumn,
}: Props): UseTransformPreviewResult => {
  const [currentRow, setCurrentRow] = useState(1);

  const rows = useMemo(() => {
    if (!fileContent) return [];
    try {
      return parseFileContent({ content: fileContent, fileType }).rows;
    } catch {
      return [];
    }
  }, [fileContent, fileType]);

  const rowIndex = Math.min(currentRow - 1, rows.length - 1);
  const sourceRow: Row | null = rows[rowIndex] ?? null;

  const rendered = useMemo(() => {
    if (!sourceRow || Object.keys(template).length === 0) return null;
    const input = generatedIdColumn
      ? { ...sourceRow, [generatedIdColumn]: placeholderId(rowIndex) }
      : sourceRow;
    return renderTemplate(template, input);
  }, [sourceRow, template, generatedIdColumn, rowIndex]);

  const totalRows = rows.length;

  // `currentRow` can outlive the file it was chosen for, so report the row actually shown.
  const displayedRow = totalRows === 0 ? currentRow : rowIndex + 1;

  const onRowChange = (row: number) => setCurrentRow(Math.min(Math.max(1, row), totalRows));

  return {
    currentRow: displayedRow,
    totalRows,
    sourceRow,
    afterRow: rendered?.row ?? null,
    approximated: rendered?.approximated ?? false,
    onRowChange,
  };
};
