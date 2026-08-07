// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { TransformFileFormFields } from '@studio/components/FilesTable/TransformFileModal/types';
import { parseFileContent, type Row } from '@studio/util/files';
import Handlebars from 'handlebars';
import { useMemo, useState } from 'react';

type Mapping = TransformFileFormFields['mappings'][number];

const UNSAFE_KEY_SEGMENTS = new Set(['__proto__', 'constructor', 'prototype']);

/**
 * Splits a free-text mapping key into path segments, rejecting keys with empty
 * or prototype-sensitive segments so traversal can never reach Object.prototype.
 */
const parseKeyParts = (key: string): string[] | null => {
  const parts = key
    .trim()
    .split('.')
    .map((part) => part.trim());

  if (parts.some((part) => part === '' || UNSAFE_KEY_SEGMENTS.has(part))) return null;

  return parts;
};

const renderMapping = (value: string | undefined, row: Record<string, unknown>): string => {
  try {
    return Handlebars.compile(value ?? '')(row);
  } catch {
    // An in-progress template (e.g. `{{name`) must not break the whole preview.
    return value ?? '';
  }
};

const applyMappings = (row: Row, mappings: Mapping[]): Row => {
  const newRow: Record<string, unknown> = {};

  const processedRow = Object.fromEntries(
    Object.entries(row).map(([k, v]) => [
      k,
      Array.isArray(v) || (typeof v === 'object' && v !== null) ? JSON.stringify(v) : v,
    ])
  );

  for (const { key, value } of mappings) {
    const keyParts = parseKeyParts(key);
    if (!keyParts) continue;

    let current = newRow;

    for (let i = 0; i < keyParts.length - 1; i++) {
      const part = keyParts[i];
      const existing = current[part];
      if (typeof existing !== 'object' || existing === null || Array.isArray(existing)) {
        current[part] = {};
      }
      current = current[part] as Record<string, unknown>;
    }

    const lastPart = keyParts[keyParts.length - 1];
    const compiledValue = renderMapping(value, processedRow);

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

  // `currentRow` can outlive the file it was chosen for, so report the row actually shown.
  const displayedRow = totalRows === 0 ? currentRow : rowIndex + 1;

  const onRowChange = (row: number) => setCurrentRow(Math.min(Math.max(1, row), totalRows));

  return {
    currentRow: displayedRow,
    totalRows,
    sourceRow,
    afterRow,
    onRowChange,
  };
};
