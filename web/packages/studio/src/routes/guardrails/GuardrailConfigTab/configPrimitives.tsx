// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { Badge, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import type { Field, Scope } from '@studio/routes/guardrails/GuardrailConfigTab/types';
import type { FC, PropsWithChildren } from 'react';

/** Muted placeholder text for empty/unconfigured regions. */
export const EmptyText: FC<PropsWithChildren> = ({ children }) => (
  <Text kind="body/regular/sm" className="text-text-secondary">
    {children}
  </Text>
);

const SCOPE_LABELS: Record<Scope, string> = {
  input: 'Input',
  output: 'Output',
  retrieval: 'Retrieval',
  tool_input: 'Tool input',
  tool_output: 'Tool output',
};

const SCOPE_COLORS: Record<Scope, 'blue' | 'purple' | 'teal' | 'gray'> = {
  input: 'blue',
  output: 'purple',
  retrieval: 'teal',
  tool_input: 'gray',
  tool_output: 'gray',
};

/** A row of stage-scope badges (Input / Output / Retrieval / Tool …). */
export const ScopeBadges: FC<{ scopes: Scope[] }> = ({ scopes }) => {
  if (scopes.length === 0) return null;
  return (
    <Flex align="center" gap="density-xs" wrap="wrap">
      {scopes.map((scope) => (
        <Badge key={scope} color={SCOPE_COLORS[scope]} kind="outline">
          {SCOPE_LABELS[scope]}
        </Badge>
      ))}
    </Flex>
  );
};

/** A vertical definition list of label/value rows. Renders nothing when empty. */
export const FieldList: FC<{ fields: Field[] }> = ({ fields }) => {
  if (fields.length === 0) return null;
  return (
    <Stack gap="density-xs">
      {fields.map((field) => (
        <KVPair
          key={field.label}
          label={field.label}
          value={field.value}
          orientation="horizontal"
          size="medium"
          truncate={false}
        />
      ))}
    </Stack>
  );
};
