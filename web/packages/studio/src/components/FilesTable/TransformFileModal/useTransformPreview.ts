// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { TransformFileFormFields } from '@studio/components/FilesTable/TransformFileModal/types';
import { parseFileContent, type Row } from '@studio/util/files';
import Handlebars from 'handlebars';
import { useMemo, useState } from 'react';

type Mapping = TransformFileFormFields['mappings'][number];

const applyMappings = (row: Row, mappings: Mapping[]): Row => {
  const newRow: Record<string, unknown> = {};

  const processedRow = Object.fromEntries(
    Object.entries(row).map(([k, v]) => [
      k,
      Array.isArray(v) || (typeof v === 'object' && v !== null) ? JSON.stringify(v) : v,
    ])
  );

  for (const { key, value } of mappings) {
    if (!key.trim()) continue;

    const template = Handlebars.compile(value ?? '');
    const keyParts = key.split('.');
    let current = newRow;

    for (let i = 0; i < keyParts.length - 1; i++) {
      const part = keyParts[i];
      if (!(part in current)) current[part] = {};
      current = current[part] as Record<string, unknown>;
    }

    const lastPart = keyParts[keyParts.length - 1];
    const compiledValue = template(processedRow);

    try {
      if (compiledValue.trim().startsWith('[') || compiledValue.trim().startsWith('{')) {
        current[lastPart] = JSON.parse(compiledValue);
      } else {
        current[lastPart] = compiledValue;
      }
    } catch {
      current[lastPart] = compiledValue;
    }
  }

  return newRow;
};

interface Props {
  fileContent: string | undefined;
  fileType: string;
  mappings: Mapping[];
}

export const useTransformPreview = ({ fileContent, fileType, mappings }: Props) => {
  const [currentRow, setCurrentRow] = useState(1);

  const rows = useMemo(() => {
    if (!fileContent) return [];
    try {
      return parseFileContent({ content: fileContent, fileType }).rows;
    } catch {
      return [];
    }
  }, [fileContent, fileType]);

  const activeMappings = useMemo(() => mappings.filter((m) => m.key.trim() !== ''), [mappings]);

  const rowIndex = Math.min(currentRow - 1, rows.length - 1);
  const sourceRow = rows[rowIndex] ?? null;

  const afterRow = useMemo(() => {
    if (!sourceRow || activeMappings.length === 0) return null;
    return applyMappings(sourceRow, activeMappings);
  }, [sourceRow, activeMappings]);

  const totalRows = rows.length;

  const onRowChange = (row: number) => setCurrentRow(Math.min(Math.max(1, row), totalRows));

  return {
    currentRow,
    totalRows,
    sourceRow,
    afterRow,
    onRowChange,
  };
};
