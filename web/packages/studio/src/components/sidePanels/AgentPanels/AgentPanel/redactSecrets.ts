// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

const SECRET_KEY = /(api[_-]?key|token|secret|password|credential|authorization)/i;
const MASK = '***';

/**
 * Deep-copy a config/card object with credential-like values masked, so the
 * Workflow tab never renders inline secrets (e.g. `llms.*.api_key`) to anyone
 * who can view the agent. Only scalar values under a secret-looking key are
 * masked; structure is preserved.
 */
export const redactSecrets = (value: unknown): unknown => {
  if (Array.isArray(value)) return value.map(redactSecrets);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, val]) => {
        if (SECRET_KEY.test(key) && (typeof val === 'string' || typeof val === 'number')) {
          return [key, MASK];
        }
        return [key, redactSecrets(val)];
      })
    );
  }
  return value;
};
