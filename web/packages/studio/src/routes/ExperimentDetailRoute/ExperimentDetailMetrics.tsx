// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { useGetExperiment } from '@nemo/sdk/generated/platform/api';
import { Divider, Flex, Text, Tooltip } from '@nvidia/foundations-react-core';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { tooltipClassName } from '@studio/styles/common';
import { type FC, type ReactNode } from 'react';

interface ExperimentDetailMetricsProps {
  experimentName: string;
}

export const ExperimentDetailMetrics: FC<ExperimentDetailMetricsProps> = ({ experimentName }) => {
  const workspace = useWorkspaceFromPath();
  const { data: experiment, isLoading } = useGetExperiment(workspace, experimentName);

  const avgCost =
    experiment?.cost_usd?.mean != null ? `$${experiment.cost_usd.mean.toFixed(3)}` : undefined;

  const avgLatency =
    experiment?.latency_ms?.mean != null
      ? `${Math.round(experiment.latency_ms.mean)} ms`
      : undefined;

  const modelNames = experiment?.model_names ?? [];
  const modelNamesJoined = modelNames.length > 0 ? modelNames.join(', ') : undefined;
  const modelNamesValue: ReactNode = modelNamesJoined ? (
    modelNames.length > 1 ? (
      // Truncate + tooltip for the multi-model case to keep the header KV row compact.
      <Tooltip slotContent={modelNamesJoined} className={tooltipClassName} side="bottom">
        <Text className="cursor-default truncate max-w-[200px] block">{modelNamesJoined}</Text>
      </Tooltip>
    ) : (
      modelNamesJoined
    )
  ) : undefined;

  return (
    <Flex align="stretch" justify="between" gap="density-3xl">
      <Flex align="stretch" gap="density-3xl">
        <KVPair
          label="Dataset Name"
          value={experiment?.dataset_name || undefined}
          loading={isLoading}
          orientation="vertical"
        />
        <Divider orientation="vertical" className="grow-0 self-stretch" />
        <KVPair
          label="Dataset Version"
          value={experiment?.dataset_version || undefined}
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
        <KVPair label="Models" value={modelNamesValue} loading={isLoading} orientation="vertical" />
        <Divider orientation="vertical" className="grow-0 self-stretch" />
        <KVPair label="Avg Cost" value={avgCost} loading={isLoading} orientation="vertical" />
        <Divider orientation="vertical" className="grow-0 self-stretch" />
        <KVPair label="Avg Latency" value={avgLatency} loading={isLoading} orientation="vertical" />
      </Flex>
    </Flex>
  );
};
