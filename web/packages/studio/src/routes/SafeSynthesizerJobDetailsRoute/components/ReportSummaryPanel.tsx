// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Dial } from '@nemo/common/src/components/Dial';
import { SafeSynthesizerSummary } from '@nemo/sdk/generated/safe-synthesizer/schema';
import { Button, Flex, Panel, Stack, Text } from '@nvidia/foundations-react-core';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getSafeSynthesizerJobReportRoute } from '@studio/routes/utils';
import { File } from 'lucide-react';
import { FC } from 'react';
import { useNavigate } from 'react-router-dom';

interface ReportSummaryPanelProps {
  jobId: string;
  jobResultSummary?: SafeSynthesizerSummary;
}

export const ReportSummaryPanel: FC<ReportSummaryPanelProps> = ({ jobId, jobResultSummary }) => {
  const navigate = useNavigate();
  const workspace = useWorkspaceFromPath();

  const sqsValue = jobResultSummary?.synthetic_data_quality_score
    ? (jobResultSummary.synthetic_data_quality_score / 10) * 100
    : 0;
  const sqsDisplay = jobResultSummary?.synthetic_data_quality_score
    ? jobResultSummary.synthetic_data_quality_score.toFixed(1)
    : '';

  const dpsValue = jobResultSummary?.data_privacy_score
    ? (jobResultSummary.data_privacy_score / 10) * 100
    : 0;
  const dpsDisplay = jobResultSummary?.data_privacy_score
    ? jobResultSummary.data_privacy_score.toFixed(1)
    : '';

  return (
    <Panel slotHeading="Report Summary" slotIcon={<File />} elevation="high" density="compact">
      <Stack gap="density-2xl" padding="density-xl" justify="between" className="overflow-hidden">
        <Flex gap="density-md" align="center" justify="around" className="w-full h-full">
          <Stack align="center" justify="center" gap="density-lg">
            <Text kind="body/semibold/md">Quality (SQS)</Text>
            <Dial
              value={sqsValue}
              displayValue={sqsDisplay}
              color="var(--color-blue-500)"
              size="l"
              scaleToFit
            />
          </Stack>
          <Stack align="center" justify="center" gap="density-lg">
            <Text kind="body/semibold/md">Privacy (DPS)</Text>
            <Dial
              value={dpsValue}
              displayValue={dpsDisplay}
              color="var(--color-purple-500)"
              size="l"
              scaleToFit
            />
          </Stack>
        </Flex>
        {jobResultSummary && (
          <Flex justify="end">
            <Button
              kind="secondary"
              onClick={() => navigate(getSafeSynthesizerJobReportRoute(workspace, jobId))}
            >
              View Report
            </Button>
          </Flex>
        )}
      </Stack>
    </Panel>
  );
};
