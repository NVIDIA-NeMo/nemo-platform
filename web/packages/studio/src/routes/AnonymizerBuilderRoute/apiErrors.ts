// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AnonymizerFormData } from '@studio/routes/AnonymizerBuilderRoute/schema';

type FormField = keyof AnonymizerFormData;

interface PydanticError {
  loc: (string | number)[];
  msg: string;
}

export interface ParsedApiError {
  fieldErrors: { field: FormField; message: string }[];
  generalMessages: string[];
}

const extractDetail = (error: unknown): PydanticError[] => {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (!Array.isArray(detail)) return [];
  return detail.filter(
    (item): item is PydanticError => typeof item?.msg === 'string' && Array.isArray(item?.loc)
  );
};

/** Map a pydantic error location to the anonymizer form field it corresponds to. */
const fieldForLoc = (loc: (string | number)[]): FormField | null => {
  const segments = loc.map(String);
  const last = segments[segments.length - 1];

  const replaceIndex = segments.indexOf('replace');
  if (replaceIndex !== -1) {
    const kind = segments[replaceIndex + 1];
    if (last === 'format_template') {
      if (kind === 'redact') return 'redactTemplate';
      if (kind === 'annotate') return 'annotateTemplate';
      if (kind === 'hash') return 'hashTemplate';
    }
    if (last === 'digest_length') return 'hashDigestLength';
    if (last === 'algorithm') return 'hashAlgorithm';
    if (last === 'normalize_label') return 'redactNormalizeLabel';
  }
  if (segments.includes('data')) {
    if (last === 'source') return 'source';
    if (last === 'text_column') return 'textColumn';
    if (last === 'data_summary') return 'dataSummary';
  }
  return null;
};

/**
 * Split a create-job API error into per-field messages (mappable to form fields
 * for inline display) and general messages (for the banner).
 */
export const parseAnonymizerApiError = (error: unknown): ParsedApiError => {
  const fieldErrors: { field: FormField; message: string }[] = [];
  const generalMessages: string[] = [];

  for (const item of extractDetail(error)) {
    const field = fieldForLoc(item.loc);
    if (field) {
      fieldErrors.push({ field, message: item.msg });
    } else {
      generalMessages.push(item.msg);
    }
  }

  return { fieldErrors, generalMessages };
};
