// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, Panel, Stack, Text } from '@nvidia/foundations-react-core';
import type { GuardrailCheckEntity } from '@studio/api/guardrail-checks/types';
import { getLatestRunStatus } from '@studio/components/dataViews/GuardrailChecksDataView/checkStatus';
import type { FC } from 'react';

interface ResultSummaryProps {
  checks: GuardrailCheckEntity[];
}

const BLOCKED_BG = 'bg-[var(--text-color-feedback-warning)]';
const ALLOWED_BG = 'bg-[var(--text-color-brand)]';
const NOTRUN_BG = 'bg-[var(--color-gray-200)]';

/** Count of checks by their latest-run verdict: allowed, blocked, or never run. */
const summarizeResults = (checks: GuardrailCheckEntity[]) => {
  let allowed = 0;
  let blocked = 0;
  let notRun = 0;

  for (const check of checks) {
    const status = getLatestRunStatus(check);
    if (status === 'success') {
      allowed += 1;
    } else if (status === 'blocked') {
      blocked += 1;
    } else {
      notRun += 1;
    }
  }

  return { allowed, blocked, notRun };
};

/** One proportional segment of the summary bar; renders nothing when its share is zero. */
const BarSegment: FC<{ colorClassName: string; pct: number }> = ({ colorClassName, pct }) =>
  pct > 0 ? (
    <div
      className={`h-full ${colorClassName}`}
      // eslint-disable-next-line no-restricted-syntax -- width is a runtime proportion
      style={{ width: `${pct}%` }}
    />
  ) : null;

/** One legend entry: a colored dot + label on the left, the count on the right. */
const LegendRow: FC<{ dotClassName: string; label: string; value: number }> = ({
  dotClassName,
  label,
  value,
}) => (
  <Flex align="center" justify="between">
    <Flex align="center" gap="density-sm">
      <span className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${dotClassName}`} />
      <Text kind="label/regular/sm">{label}</Text>
    </Flex>
    <Text kind="label/bold/sm">{value}</Text>
  </Flex>
);

/** Proportional bar + legend breaking down a set of checks by their latest-run verdict. */
export const ResultSummary: FC<ResultSummaryProps> = ({ checks }) => {
  const { allowed, blocked, notRun } = summarizeResults(checks);

  // Bar proportions span every check: blocked, then allowed, then not-run at the end.
  const total = blocked + allowed + notRun;
  const pct = (n: number) => (total > 0 ? (n / total) * 100 : 0);

  return (
    <Panel slotHeading="Result Summary">
      <Stack gap="density-lg">
        <Flex
          className=" h-3 overflow-hidden rounded-full bg-surface-sunken"
          role="img"
          gap="0.5"
          aria-label={`${blocked} blocked, ${allowed} allowed, ${notRun} not run`}
        >
          <BarSegment colorClassName={BLOCKED_BG} pct={pct(blocked)} />
          <BarSegment colorClassName={ALLOWED_BG} pct={pct(allowed)} />
          <BarSegment colorClassName={NOTRUN_BG} pct={pct(notRun)} />
        </Flex>
        <Stack gap="density-sm">
          <LegendRow dotClassName={BLOCKED_BG} label="Blocked" value={blocked} />
          <LegendRow dotClassName={ALLOWED_BG} label="Allowed" value={allowed} />
          <LegendRow dotClassName={NOTRUN_BG} label="Not run" value={notRun} />
        </Stack>
      </Stack>
    </Panel>
  );
};
