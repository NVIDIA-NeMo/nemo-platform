// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfigOutput } from '@nemo/sdk/generated/platform/schema';
import { Divider, Flex, Stack, StatusIndicator, Text } from '@nvidia/foundations-react-core';
import type { RunRecord } from '@studio/api/guardrail-checks/types';
import {
  describeRailKey,
  getActivatedGuardrails,
} from '@studio/components/sidePanels/GuardrailCheckDetailSidePanel/railLabels';
import { RailStatusBadge } from '@studio/components/sidePanels/GuardrailCheckDetailSidePanel/RailStatusBadge';
import cn from 'classnames';
import type { FC } from 'react';

/** Pins the Status header over the badge column so the two stay aligned. */
const STATUS_COLUMN = 'w-[149px]';

export interface RailStatusTabProps {
  latestRun: RunRecord | undefined;
  configData: RailsConfigOutput | undefined;
}

/**
 * Per-rail outcome of the most recent run, followed by the config's declared
 * guardrail coverage.
 *
 * The two sections answer different questions: the table is what *ran*, the
 * indicator list is what the config *declares* — so a guardrail the run never
 * exercised still appears, dimmed, instead of silently vanishing.
 */
export const RailStatusTab: FC<RailStatusTabProps> = ({ latestRun, configData }) => {
  // Not gated on a run: the guardrails below come from the config, so a check
  // that has never run still shows its declared coverage, all of it inactive.
  const railEntries = Object.entries(latestRun?.rails_status ?? {});
  const guardrails = getActivatedGuardrails(configData, latestRun?.rails_status);

  return (
    <Stack gap="density-xl">
      {railEntries.length > 0 ? (
        <Stack gap="0">
          <Flex className="border-b-2 border-base py-density-sm" align="center" justify="between">
            <Text kind="label/bold/md">Rail Type</Text>
            <Text kind="label/bold/md" className={STATUS_COLUMN}>
              Status
            </Text>
          </Flex>
          {railEntries.map(([name, railStatus]) => (
            <Flex
              key={name}
              align="center"
              justify="between"
              className="border-b border-base py-density-sm last:border-0"
            >
              <Text kind="body/regular/md">{describeRailKey(name)}</Text>
              <div className={STATUS_COLUMN}>
                <RailStatusBadge status={railStatus.status} />
              </div>
            </Flex>
          ))}
        </Stack>
      ) : (
        <Text kind="body/regular/sm" className="text-secondary">
          {latestRun ? 'No rail data available.' : 'No runs yet.'}
        </Text>
      )}

      {guardrails.length > 0 && (
        <>
          <Divider />
          <Stack gap="density-md">
            <Text kind="label/semibold/lg">Activated Guardrails</Text>
            <Stack gap="density-sm">
              {guardrails.map(({ id, label, active }) => (
                <Flex key={id} align="center" gap="density-sm">
                  {/* KUI ships no neutral dot, so the inactive one borrows its
                      label's disabled token through the component's --color. */}
                  <StatusIndicator
                    size="small"
                    color={active ? 'green' : null}
                    className={cn('shrink-0', !active && '[--color:var(--text-color-disabled)]')}
                  />
                  <Text kind="body/semibold/md" className={active ? undefined : 'text-disabled'}>
                    {label}
                  </Text>
                </Flex>
              ))}
            </Stack>
          </Stack>
        </>
      )}
    </Stack>
  );
};
