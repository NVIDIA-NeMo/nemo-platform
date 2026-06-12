// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AcceptedFileType } from '@nemo/common/src/components/DatasetFileSelect/DatasetFileSelect';

const ALLOWED_ACCEPTED_FILE_TYPES = new Set<AcceptedFileType>([
  '.json',
  '.jsonl',
  '.csv',
  '.parquet',
  '.yml',
  '.yaml',
]);

const isAcceptedFileType = (value: string): value is AcceptedFileType =>
  ALLOWED_ACCEPTED_FILE_TYPES.has(value as AcceptedFileType);

export const getStringValue = (input: Record<string, unknown>, key: string): string | undefined => {
  const value = input[key];
  if (typeof value !== 'string') return undefined;
  const trimmed = value.trim();
  return trimmed || undefined;
};

export const getOutputKey = (input: Record<string, unknown>, fallback: string): string => {
  const outputKey = getStringValue(input, 'output_key') ?? getStringValue(input, 'value_key');
  if (!outputKey || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(outputKey)) return fallback;
  return outputKey;
};

export const getAcceptedFileTypes = (
  input: Record<string, unknown>,
  fallback: AcceptedFileType[]
): AcceptedFileType[] => {
  const raw = input.accepted_file_types;
  if (!Array.isArray(raw)) return fallback;
  const accepted = raw.filter(
    (item): item is AcceptedFileType => typeof item === 'string' && isAcceptedFileType(item)
  );
  return accepted.length ? accepted : fallback;
};
