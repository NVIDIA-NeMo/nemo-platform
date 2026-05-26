// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { EntryFilter } from '@nemo/sdk/generated/platform/schema';
import { QUERY_PARAMETERS } from '@studio/routes/constants';
import { ChatCompletionMessageParam } from 'openai/resources/index.mjs';

/**
 * Recursively processes a filter object and adds its properties to URLSearchParams.
 * Handles nested objects, arrays with operators (like 'in'), and primitive values.
 *
 * @param obj - The object to process
 * @param params - The URLSearchParams instance to populate
 * @param prefix - The current key prefix for nested properties (e.g., 'context', 'created_at')
 */
const processFilterObject = (obj: EntryFilter, params: URLSearchParams, prefix = ''): void => {
  for (const [key, value] of Object.entries(obj)) {
    // Skip undefined and null values
    if (value === undefined || value === null) {
      continue;
    }

    // Build the parameter key (e.g., 'context.app', 'created_at.gte')
    const paramKey = prefix ? `${prefix}.${key}` : key;

    // Handle array values with operators (e.g., {in: ['id1', 'id2']})
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item !== undefined && item !== null) {
          params.append(paramKey, String(item));
        }
      });
    }
    // Handle nested objects recursively
    else if (typeof value === 'object' && value !== null) {
      processFilterObject(value, params, paramKey);
    }
    // Handle primitive values (string, number, boolean)
    else {
      params.set(paramKey, String(value));
    }
  }
};

export const generateFilterParam = (filter?: EntryFilter): string => {
  if (!filter) {
    return '';
  }
  const params = new URLSearchParams();

  // Special handling for 'project' field to use QUERY_PARAMETERS constant
  if (filter.project && typeof filter.project === 'string') {
    params.set(QUERY_PARAMETERS.project, filter.project);
    const withoutProject = { ...filter, project: undefined };
    processFilterObject(withoutProject, params);
  } else {
    processFilterObject(filter, params);
  }

  return params.toString();
};

export const isToolCallMessage = (message: ChatCompletionMessageParam) => {
  return (
    message.role === 'tool' ||
    ('tool_calls' in message && Array.isArray(message.tool_calls) && message.tool_calls.length > 0)
  );
};
