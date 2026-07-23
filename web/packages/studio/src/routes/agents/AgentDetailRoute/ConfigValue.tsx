// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { Stack, Text } from '@nvidia/foundations-react-core';
import { humanizeKey } from '@studio/routes/agents/AgentDetailRoute/configFormat';
import type { FC } from 'react';

const SENSITIVE_KEY = /(api[_-]?key|secret|token|password|passwd|credential)/i;
const MASK = '••••••••';

/** Keys that match SENSITIVE_KEY on substring but are ordinary config, not secrets. */
const NON_SENSITIVE_KEYS = new Set([
  'max_tokens',
  'max_new_tokens',
  'max_input_tokens',
  'max_output_tokens',
  'max_completion_tokens',
  'max_prompt_tokens',
  'num_tokens',
  'token_limit',
  'context_window_tokens',
]);

const isSensitiveKey = (key: string): boolean =>
  !NON_SENSITIVE_KEYS.has(key.toLowerCase()) && SENSITIVE_KEY.test(key);

const isScalar = (value: unknown): boolean =>
  value === null || ['string', 'number', 'boolean'].includes(typeof value);

const formatScalar = (value: unknown): string => {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  return String(value);
};

interface ConfigValueProps {
  label: string;
  value: unknown;
}

/**
 * Recursively renders an arbitrary config value as KVPair rows. Scalars (and
 * scalar-only arrays) collapse to a single row; nested objects/arrays indent.
 * Values under sensitive keys (api_key, token, secret, …) are masked.
 */
export const ConfigValue: FC<ConfigValueProps> = ({ label, value }) => {
  const heading = humanizeKey(label);

  if (isSensitiveKey(label) && value != null && value !== '') {
    return <KVPair label={heading} value={MASK} />;
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return <KVPair label={heading} value="—" />;
    if (value.every(isScalar)) {
      return <KVPair label={heading} value={value.map(formatScalar).join(', ')} />;
    }
    return (
      <NestedBlock heading={heading}>
        {value.map((item, index) => (
          <ConfigValue key={index} label={`${index + 1}`} value={item} />
        ))}
      </NestedBlock>
    );
  }

  if (value !== null && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return <KVPair label={heading} value="—" />;
    return (
      <NestedBlock heading={heading}>
        {entries.map(([childKey, childValue]) => (
          <ConfigValue key={childKey} label={childKey} value={childValue} />
        ))}
      </NestedBlock>
    );
  }

  return <KVPair label={heading} value={formatScalar(value)} />;
};

const NestedBlock: FC<{ heading: string; children: React.ReactNode }> = ({ heading, children }) => (
  <Stack gap="1">
    <Text kind="label/regular/sm" className="text-secondary">
      {heading}
    </Text>
    <Stack gap="2" className="border-l border-base pl-3">
      {children}
    </Stack>
  </Stack>
);
