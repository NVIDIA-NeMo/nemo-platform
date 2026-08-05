// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { Badge, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import type { RunRecord } from '@studio/api/guardrail-checks/types';
import { ResultIndicator } from '@studio/components/dataViews/GuardrailChecksDataView/ResultIndicator';
import { describeRailKey } from '@studio/components/sidePanels/GuardrailCheckDetailSidePanel/railLabels';
import { RailStatusBadge } from '@studio/components/sidePanels/GuardrailCheckDetailSidePanel/RailStatusBadge';
import type { FC } from 'react';

export interface RunHistoryTabProps {
  readonly runs: RunRecord[];
}

/**
 * Every recorded run of a check, newest first.
 *
 * Each entry carries the config version it ran against, because a config can
 * be edited between runs — without that, two rows with different verdicts look
 * like flakiness rather than a config change.
 */
export const RunHistoryTab: FC<RunHistoryTabProps> = ({ runs }) => {
  // `runs` is appended to on each execution, so reversing yields newest-first.
  const sorted = [...runs].reverse();

  if (sorted.length === 0) {
    return (
      <Text kind="body/regular/sm" className="text-secondary">
        No runs recorded yet.
      </Text>
    );
  }

  return (
    <Stack gap="0">
      {sorted.map((run) => {
        const railEntries = Object.entries(run.rails_status ?? {});
        return (
          // Keyed by timestamp, not index: newest sorts first, so every index
          // shifts when a run is appended and index keys would remount the list.
          <Stack
            key={run.run_at}
            gap="density-sm"
            className="border-b border-base py-density-md last:border-0"
          >
            <Flex align="center" justify="between">
              <Flex align="center" gap="density-sm">
                <ResultIndicator status={run.status} />
                {run.config_version !== undefined && (
                  <Badge color="gray" kind="outline">
                    v{run.config_version}
                  </Badge>
                )}
              </Flex>
              <RelativeTime datetime={run.run_at} focusableForTooltip={false} />
            </Flex>
            {railEntries.length > 0 && (
              <Stack gap="density-xs" className="pl-density-sm">
                {railEntries.map(([name, railStatus]) => (
                  <Flex key={name} align="center" justify="between">
                    <Text kind="body/regular/sm" className="text-secondary">
                      {describeRailKey(name)}
                    </Text>
                    <RailStatusBadge status={railStatus.status} />
                  </Flex>
                ))}
              </Stack>
            )}
          </Stack>
        );
      })}
    </Stack>
  );
};
