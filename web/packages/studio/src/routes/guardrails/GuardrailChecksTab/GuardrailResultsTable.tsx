// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  Badge,
  Flex,
  Panel,
  Stack,
  TableBody,
  TableDataCell,
  TableHead,
  TableHeaderCell,
  TableRoot,
  TableRow,
  Text,
} from '@nvidia/foundations-react-core';
import type { GuardrailCheckEntity, Verdict } from '@studio/api/guardrail-checks/types';
import {
  getCheckInputText,
  getCheckOutputText,
} from '@studio/components/dataViews/GuardrailChecksDataView/checkMessages';
import { getLatestRunStatus } from '@studio/components/dataViews/GuardrailChecksDataView/checkStatus';
import { ArrowRight, Clock, ShieldCheck } from 'lucide-react';
import type { FC } from 'react';

interface GuardrailResultsTableProps {
  checks: GuardrailCheckEntity[];
}

/** Segment/legend colors for the result summary: purple guarded, green allowed, gray not-run. */
const GUARDED_BG = 'bg-[var(--color-purple-600)]';
const ALLOWED_BG = 'bg-[var(--color-green-200)]';
const NOTRUN_BG = 'bg-[var(--color-gray-200)]';

/** Count of checks by their latest-run verdict: allowed, guarded, or never run. */
const summarizeResults = (checks: GuardrailCheckEntity[]) => {
  let allowed = 0;
  let guarded = 0;
  let notRun = 0;

  for (const check of checks) {
    const status = getLatestRunStatus(check);
    if (status === 'success') {
      allowed += 1;
    } else if (status === 'blocked') {
      guarded += 1;
    } else {
      notRun += 1;
    }
  }

  return { allowed, guarded, notRun };
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

/** Solid status badge for a check's latest-run verdict (purple guarded / gray allowed). */
const ResultIndicator: FC<{ status: Verdict | undefined }> = ({ status }) => {
  if (status === 'blocked') {
    return (
      <Badge color="purple" kind="solid">
        <ShieldCheck size={14} />
        Guarded
      </Badge>
    );
  }
  if (status === 'success') {
    return (
      <Badge color="green" kind="solid">
        <ArrowRight size={14} />
        Allowed
      </Badge>
    );
  }
  return (
    <Badge color="gray" kind="solid">
      <Clock size={14} />
      Not run
    </Badge>
  );
};

export const GuardrailResultsTable: FC<GuardrailResultsTableProps> = ({ checks }) => {
  const { allowed, guarded, notRun } = summarizeResults(checks);

  // Bar proportions span every check: guarded, then allowed, then not-run at the end.
  const total = guarded + allowed + notRun;
  const pct = (n: number) => (total > 0 ? (n / total) * 100 : 0);

  return (
    <Stack gap="density-lg" className="w-full min-h-0">
      {/* ── Result Summary ─────────────────────────── */}
      <Panel slotHeading="Result Summary">
        <Stack gap="density-lg">
          {/* Left → right: guarded (purple), allowed (green), not-run (gray) at the end. */}
          <div
            className="flex h-2 w-full overflow-hidden rounded-full bg-surface-sunken"
            role="img"
            aria-label={`${guarded} guarded, ${allowed} allowed, ${notRun} not run`}
          >
            <BarSegment colorClassName={GUARDED_BG} pct={pct(guarded)} />
            <BarSegment colorClassName={ALLOWED_BG} pct={pct(allowed)} />
            <BarSegment colorClassName={NOTRUN_BG} pct={pct(notRun)} />
          </div>
          <Stack gap="density-sm">
            <LegendRow dotClassName={GUARDED_BG} label="Guarded" value={guarded} />
            <LegendRow dotClassName={ALLOWED_BG} label="Allowed" value={allowed} />
            <LegendRow dotClassName={NOTRUN_BG} label="Not run" value={notRun} />
          </Stack>
        </Stack>
      </Panel>

      {/* ── Results table ──────────────────────────── */}
      <Panel className="py-0">
        <TableRoot layout="fixed" align="left" className="w-full">
          <TableHead>
            <TableRow>
              <TableHeaderCell>Input</TableHeaderCell>
              <TableHeaderCell>Output</TableHeaderCell>
              <TableHeaderCell className="w-[160px]">Result</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {checks.length === 0 ? (
              <TableRow>
                <TableDataCell colSpan={3}>
                  <Text className="text-text-secondary">No tests yet.</Text>
                </TableDataCell>
              </TableRow>
            ) : (
              checks.map((check) => {
                const input = getCheckInputText(check.data.messages);
                const output = getCheckOutputText(check.data.messages);
                const status = getLatestRunStatus(check);
                return (
                  <TableRow key={check.id}>
                    <TableDataCell>
                      <Text className="truncate" title={input}>
                        {input || '—'}
                      </Text>
                    </TableDataCell>
                    <TableDataCell>
                      <Text className="truncate" title={output}>
                        {output || '—'}
                      </Text>
                    </TableDataCell>
                    <TableDataCell>
                      <ResultIndicator status={status} />
                    </TableDataCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </TableRoot>
      </Panel>
    </Stack>
  );
};
