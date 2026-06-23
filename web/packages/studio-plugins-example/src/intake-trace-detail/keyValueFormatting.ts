// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { formatInteger, formatMaybe } from '@studio/util/intakeTelemetry';
import type { ReactNode } from 'react';

/** True for non-empty scalars and non-empty objects/arrays. */
export const isMeaningfulValue = (value: unknown): value is string | number | boolean => {
  if (value === null || value === undefined || value === '') {
    return false;
  }
  if (typeof value === 'object') {
    if (Array.isArray(value)) {
      return value.length > 0;
    }
    return Object.keys(value).length > 0;
  }
  return true;
};

export const formatUnknownKeyValue = (value: unknown): ReactNode => {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? formatInteger(value) : String(value);
  }
  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No';
  }
  if (typeof value === 'string') {
    return value;
  }
  if (typeof value === 'object' && value !== null) {
    return JSON.stringify(value, null, 2);
  }
  return formatMaybe(value as string | null | undefined);
};
