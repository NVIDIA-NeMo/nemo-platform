// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { LogViewer } from '@nemo/common/src/components/LogViewer';
import { useJobLogs } from '@nemo/common/src/hooks/useJobLogs';
import type { PlatformJobStatus } from '@nemo/sdk/generated/platform/schema';
import { Button, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { formatPipelineStepName } from '@studio/util/customizationFailure';
import type { FC } from 'react';

interface Props {
  customizationJobName: string;
  workspace: string;
  jobStatus?: PlatformJobStatus;
  /** Pipeline step to scope logs to, e.g. `grpo-training`. */
  stepId?: string;
  onClearStepFilter?: () => void;
}

export const LogsTab: FC<Props> = ({
  customizationJobName,
  workspace,
  jobStatus,
  stepId,
  onClearStepFilter,
}) => {
  const { data: logs, isLoading } = useJobLogs({
    workspace,
    name: customizationJobName,
    jobStatus,
    stepId,
  });

  return (
    <Stack className="min-h-0 w-full flex-1 pt-4" gap="density-md">
      {stepId && (
        // Without this the filtered view is indistinguishable from a job that logged very little.
        <Flex align="center" justify="between" gap="density-md" className="shrink-0">
          <Text kind="body/regular/sm" className="text-secondary">
            Showing logs for {formatPipelineStepName(stepId)}
          </Text>
          {onClearStepFilter && (
            <Button kind="tertiary" size="small" onClick={onClearStepFilter}>
              Show all logs
            </Button>
          )}
        </Flex>
      )}
      <Flex className="min-h-0 w-full flex-1">
        <LogViewer
          logs={logs ?? []}
          isLoading={isLoading}
          downloadFilename={
            stepId ? `${customizationJobName}-${stepId}.log` : `${customizationJobName}.log`
          }
          fillHeight
        />
      </Flex>
    </Stack>
  );
};
