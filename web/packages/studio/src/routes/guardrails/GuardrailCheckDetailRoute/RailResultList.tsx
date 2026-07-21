// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsOutput } from '@nemo/sdk/generated/platform/schema';
import { Badge, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import type { RunRecord } from '@studio/api/guardrail-checks/types';
import {
  buildRailRows,
  type RailVerdict,
} from '@studio/routes/guardrails/GuardrailCheckDetailRoute/railRows';
import type { FC } from 'react';

const RailVerdictBadge: FC<{ verdict: RailVerdict }> = ({ verdict }) => {
  if (verdict === 'allowed') {
    return (
      <Badge color="green" kind="solid">
        Allowed
      </Badge>
    );
  }
  if (verdict === 'guarded') {
    return (
      <Badge color="red" kind="solid">
        Guarded
      </Badge>
    );
  }
  return (
    <Badge color="gray" kind="outline">
      Skipped
    </Badge>
  );
};

export interface RailResultListProps {
  rails: RailsOutput | undefined;
  /** The latest run, or undefined if the check has never been run. */
  run: RunRecord | undefined;
}

export const RailResultList: FC<RailResultListProps> = ({ rails, run }) => {
  const rows = buildRailRows(rails, run);

  if (rows.length === 0) {
    return <Text className="text-text-secondary">No rails configured on this guardrail.</Text>;
  }

  return (
    <Stack gap="0" role="list">
      {rows.map((row, index) => (
        <Flex
          key={row.name}
          role="listitem"
          align="center"
          justify="between"
          gap="density-md"
          className={index === 0 ? 'py-density-sm' : 'py-density-sm border-t border-border-subtle'}
        >
          <Text className="min-w-0 truncate" title={row.name}>
            {row.name}
          </Text>
          <RailVerdictBadge verdict={row.verdict} />
        </Flex>
      ))}
    </Stack>
  );
};
