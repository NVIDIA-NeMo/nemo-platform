// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Row } from '@studio/util/files';
import { websiteLogger } from '@studio/util/logger';
import Papa from 'papaparse';

/**
 * Returns a formatted string with count and properly pluralized text.
 * @param text - The singular form of the word (e.g., "entry", "file")
 * @param count - The number to display
 * @param plural - Optional custom plural form for irregular words (e.g., "entries", "children").
 *                 If not provided, defaults to appending 's' to the text.
 * @returns Formatted string like "1 entry" or "3 entries"
 * @example
 * getTextWithCount('file', 1)           // "1 file"
 * getTextWithCount('file', 3)           // "3 files"
 * getTextWithCount('entry', 2, 'entries') // "2 entries"
 */
export const getTextWithCount = (text: string, count: number, plural?: string) => {
  const pluralForm = plural ?? `${text}s`;
  return `${count} ${count !== 1 ? pluralForm : text}`;
};

export const capitalize = (str: string) => {
  return str.charAt(0).toUpperCase() + str.slice(1);
};

/**
 * Formats a snake_case key into a human-readable label.
 * @param key - The snake_case key to format (e.g., "prompt_tokens")
 * @returns A title-cased label with spaces (e.g., "Prompt Tokens")
 * @example
 * formatKeyLabel('prompt_tokens')     // "Prompt Tokens"
 * formatKeyLabel('total_tokens')      // "Total Tokens"
 * formatKeyLabel('finish_reason')     // "Finish Reason"
 */
export const formatKeyLabel = (key: string): string => {
  return key.split('_').map(capitalize).join(' ');
};

/**
 * Parses a CSV string and returns an array of objects.
 * @param csvString - The CSV string to parse.
 * @returns An array of objects.
 */
export const parseCSV = (props: { csvString: string; options: Papa.ParseConfig }): Row[] => {
  const { csvString, options } = props;
  const { data, errors } = Papa.parse(csvString, options);

  if (errors.length) {
    websiteLogger.error(`CSV Parse Errors: ${JSON.stringify(errors)}`);
    return [];
  }

  return data;
};
