// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import {
  Flex,
  Stack,
  TabsContent,
  TabsList,
  TabsRoot,
  TabsTrigger,
  Text,
} from '@nvidia/foundations-react-core';
import type { GuardrailCheckEntity } from '@studio/api/guardrail-checks/types';
import { getLatestRunStatus } from '@studio/components/dataViews/GuardrailChecksDataView/checkStatus';
import { ResultIndicator } from '@studio/components/dataViews/GuardrailChecksDataView/ResultIndicator';
import { RailStatusTab } from '@studio/components/sidePanels/GuardrailCheckDetailSidePanel/RailStatusTab';
import { RunHistoryTab } from '@studio/components/sidePanels/GuardrailCheckDetailSidePanel/RunHistoryTab';
import cn from 'classnames';
import type { FC } from 'react';

export interface ResultsPaneProps {
  readonly check: GuardrailCheckEntity;
  readonly configData: RailsConfig | undefined;
  readonly checkIndex: number;
  readonly className?: string;
}

/**
 * A check's verdict and results, split across a latest-run view and a history view.
 *
 * These tabs are uncontrolled local state, unlike the Tests/Test Results switcher
 * on the page behind the panel — that one is routed, and a view *inside* a detail
 * panel is not worth a history entry.
 */
export const ResultsPane: FC<ResultsPaneProps> = ({ check, configData, checkIndex, className }) => {
  const { runs } = check.data;
  const latestStatus = getLatestRunStatus(check);
  const latestRun = runs.length > 0 ? runs[runs.length - 1] : undefined;

  return (
    <Stack gap="density-xl" className={cn('overflow-auto p-density-xl', className)}>
      <Flex align="center" gap="density-md">
        <Text kind="body/bold/2xl">Test {checkIndex + 1}</Text>
        <ResultIndicator status={latestStatus} />
      </Flex>

      <TabsRoot defaultValue="rail-status">
        <TabsList aria-label="Test result views">
          <TabsTrigger value="rail-status">Rail Status</TabsTrigger>
          <TabsTrigger value="run-history">Run History</TabsTrigger>
        </TabsList>

        <TabsContent value="rail-status" className="items-stretch p-0 pt-density-lg">
          <RailStatusTab latestRun={latestRun} configData={configData} />
        </TabsContent>

        <TabsContent value="run-history" className="items-stretch p-0 pt-density-lg">
          <RunHistoryTab runs={runs} />
        </TabsContent>
      </TabsRoot>
    </Stack>
  );
};
