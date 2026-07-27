// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Badge, Card, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import type {
  ValidationAttackRow,
  ValidationBenignRow,
  ValidationReport,
} from '@studio/components/ironSwarm/useSanityCheck';
import { FC } from 'react';

// Maps a per-item status to a badge (green = good, yellow = bad, gray = error/neutral).
const attackBadge = (status?: string) =>
  status === 'blocked' ? (
    <Badge color="green">Blocked</Badge>
  ) : status === 'not_blocked' ? (
    <Badge color="yellow">Not blocked</Badge>
  ) : (
    <Badge color="gray">Error</Badge>
  );

const benignBadge = (status?: string) =>
  status === 'passed' ? (
    <Badge color="green">Passed</Badge>
  ) : status === 'refused' ? (
    <Badge color="yellow">Wrongly blocked</Badge>
  ) : (
    <Badge color="gray">Error</Badge>
  );

const Stat: FC<{ label: string; value: string; good: boolean }> = ({ label, value, good }) => (
  <Card className="flex-1 p-4">
    <Stack gap="density-xs">
      <Text kind="body/regular/sm" className="text-gray-400">
        {label}
      </Text>
      <Text kind="title/lg" className={good ? 'text-green-400' : 'text-yellow-400'}>
        {value}
      </Text>
    </Stack>
  </Card>
);

const AttackRow: FC<{ row: ValidationAttackRow }> = ({ row }) => (
  <Flex justify="between" align="start" gap="density-md" className="py-2">
    <Stack gap="density-xxs" className="min-w-0">
      <Text kind="body/semibold/sm">{row.probe ?? row.attack_id ?? 'attack'}</Text>
      {row.goal ? (
        <Text kind="body/regular/sm" className="truncate text-gray-400">
          {row.goal}
        </Text>
      ) : null}
      {row.prompt_excerpt ? (
        <Text kind="body/regular/xs" className="truncate text-gray-500">
          {row.prompt_excerpt}
        </Text>
      ) : null}
    </Stack>
    <div className="shrink-0">{attackBadge(row.status)}</div>
  </Flex>
);

const BenignRow: FC<{ row: ValidationBenignRow }> = ({ row }) => (
  <Flex justify="between" align="start" gap="density-md" className="py-2">
    <Stack gap="density-xxs" className="min-w-0">
      <Text kind="body/semibold/sm">{row.tool ?? row.label ?? `request ${row.index ?? ''}`}</Text>
      {row.payload_excerpt ? (
        <Text kind="body/regular/xs" className="truncate text-gray-500">
          {row.payload_excerpt}
        </Text>
      ) : null}
    </Stack>
    <div className="shrink-0">{benignBadge(row.status)}</div>
  </Flex>
);

interface SanityCheckReportProps {
  report: ValidationReport;
}

// The sanity-check scorecard: how many recorded attacks the chosen defenses now block, and how many benign
// requests they wrongly block (false positives), with a per-item breakdown.
export const SanityCheckReport: FC<SanityCheckReportProps> = ({ report }) => {
  const { summary, attacks, benign } = report;
  const attacksGood = summary.attacks_blocked === summary.attacks_total;
  const benignGood = summary.benign_false_positives === 0;

  return (
    <Stack gap="density-xl">
      <Flex gap="density-md">
        <Stat
          label="Attacks blocked"
          value={`${summary.attacks_blocked} / ${summary.attacks_total}`}
          good={attacksGood}
        />
        <Stat
          label="Benign preserved"
          value={
            summary.benign_false_positives === 0
              ? `${summary.benign_total} / ${summary.benign_total}`
              : `${summary.benign_total - summary.benign_false_positives} / ${summary.benign_total} · ${summary.benign_false_positives} false positive${summary.benign_false_positives === 1 ? '' : 's'}`
          }
          good={benignGood}
        />
      </Flex>

      {attacks.length > 0 ? (
        <Stack gap="density-xs">
          <Text kind="body/semibold/md">Attacks ({attacks.length})</Text>
          <Card className="p-3 [&>*+*]:border-t [&>*+*]:border-gray-700">
            {attacks.map((row, i) => (
              <AttackRow key={row.attack_id ?? i} row={row} />
            ))}
          </Card>
        </Stack>
      ) : null}

      {benign.length > 0 ? (
        <Stack gap="density-xs">
          <Text kind="body/semibold/md">Benign requests ({benign.length})</Text>
          <Card className="p-3 [&>*+*]:border-t [&>*+*]:border-gray-700">
            {benign.map((row, i) => (
              <BenignRow key={row.index ?? i} row={row} />
            ))}
          </Card>
        </Stack>
      ) : null}
    </Stack>
  );
};
