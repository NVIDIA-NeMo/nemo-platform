// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { Stack, Text } from '@nvidia/foundations-react-core';
import { LLMJudgeDisplay } from '@studio/components/evaluation/Configurations/LLMJudgeDisplay';
import { MetricDisplay } from '@studio/components/evaluation/Configurations/MetricDisplay';
import { DatasetFileLink } from '@studio/components/evaluation/DatasetFileLink';
import {
  getTaskFilesetInfo,
  getTaskMetrics,
  getTaskTargetTypeDisplay,
  type TaskConfigInput,
} from '@studio/selectors/evaluationConfig';
import { FC } from 'react';

/**
 * Component to display a single evaluation task with all its details.
 * Shows task name, target type, input file, and associated metrics.
 *
 * @param props.taskName - Name of the task
 * @param props.task - Task configuration object containing type, dataset, and metrics
 * @param props.workspace - workspace reference for generating fileset file links
 */
export const TaskDisplay: FC<{
  taskName: string;
  task: TaskConfigInput;
  workspace: string;
}> = ({ taskName, task, workspace }) => {
  const targetType = getTaskTargetTypeDisplay(task);
  const metrics = getTaskMetrics(task);
  const metricEntries = Object.entries(metrics);

  // Get fileset info with parsed URL and link
  const filesetInfo = getTaskFilesetInfo(taskName, task, workspace);

  return (
    <Stack gap="density-xl" className="w-full">
      <KVPair label="Task Name" value={taskName} />
      <KVPair label="Target Type" value={targetType} />
      {filesetInfo && (
        <KVPair
          label="Input File"
          value={<DatasetFileLink label={filesetInfo.fileDisplayName} url={filesetInfo.linkUrl} />}
        />
      )}

      {/* Metrics Section */}
      {metricEntries.length > 0 && (
        <Stack gap="density-2xl" className="w-full">
          <Text kind="label/regular/md" className="text-subtle">
            Metrics
          </Text>
          <Stack gap="density-2xl" className="w-full pl-density-lg">
            {metricEntries.map(([metricKey, metricConfig]) => {
              const config = {
                type: metricConfig.type ?? '',
                params: (metricConfig as { params?: Record<string, unknown> }).params,
              };
              return (
                <Stack key={metricKey} gap="density-xl">
                  {metricConfig.type?.toLowerCase() === 'llm-judge' ? (
                    <LLMJudgeDisplay metricName={metricKey} metricConfig={config} />
                  ) : (
                    <MetricDisplay metricName={metricKey} metricConfig={config} />
                  )}
                </Stack>
              );
            })}
          </Stack>
        </Stack>
      )}
    </Stack>
  );
};
