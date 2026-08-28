// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { formatDurationMs } from '@nemo/common/src/utils/date';
import { useGetEvaluation } from '@nemo/sdk/generated/platform/api';
import { Divider, Flex, Tooltip } from '@nvidia/foundations-react-core';
import { ChangesetBadge } from '@studio/components/ChangesetBadge';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { tooltipClassName } from '@studio/styles/common';
import { type FC } from 'react';

interface EvaluationDetailMetricsProps {
  evaluationName: string;
}

export const EvaluationDetailMetrics: FC<EvaluationDetailMetricsProps> = ({ evaluationName }) => {
  const workspace = useWorkspaceFromPath();
  const { data: experiment, isLoading } = useGetEvaluation(workspace, evaluationName);

  // formatDurationMs returns '—' for null/undefined, which is also KVPair's default empty value.
  const avgDuration = formatDurationMs(experiment?.latency_ms?.mean);

  const tokenSum = experiment?.tokens?.sum;
  const totalTokens =
    tokenSum != null
      ? Math.round(tokenSum).toLocaleString(undefined, {
          notation: 'compact',
          maximumFractionDigits: 0,
        })
      : undefined;

  return (
    <Flex align="stretch" justify="between" gap="density-3xl">
      <Flex align="stretch" gap="density-3xl">
        {experiment?.source_link ? (
          <>
            <KVPair
              label="Source"
              value={<ChangesetBadge href={experiment.source_link} />}
              loading={isLoading}
              orientation="vertical"
            />
            <Divider orientation="vertical" className="grow-0 self-stretch" />
          </>
        ) : null}
        <KVPair
          label="Dataset Name"
          value={
            experiment?.dataset_name ? (
              experiment.dataset_version ? (
                <Tooltip
                  slotContent={`Version: ${experiment.dataset_version}`}
                  className={tooltipClassName}
                  side="bottom"
                >
                  <span className="cursor-default">{experiment.dataset_name}</span>
                </Tooltip>
              ) : (
                experiment.dataset_name
              )
            ) : undefined
          }
          loading={isLoading}
          orientation="vertical"
        />
        <Divider orientation="vertical" className="grow-0 self-stretch" />
        <KVPair
          label="Created"
          value={
            experiment?.created_at ? <RelativeTime datetime={experiment.created_at} /> : undefined
          }
          loading={isLoading}
          orientation="vertical"
        />
        <Divider orientation="vertical" className="grow-0 self-stretch" />
        <KVPair
          label="Updated"
          value={
            experiment?.updated_at ? <RelativeTime datetime={experiment.updated_at} /> : undefined
          }
          loading={isLoading}
          orientation="vertical"
        />
      </Flex>
      <Flex align="stretch" gap="density-3xl">
        <KVPair label="Tokens" value={totalTokens} loading={isLoading} orientation="vertical" />
        <Divider orientation="vertical" className="grow-0 self-stretch" />
        <KVPair
          label="Avg Duration"
          value={avgDuration}
          loading={isLoading}
          orientation="vertical"
        />
      </Flex>
    </Flex>
  );
};
