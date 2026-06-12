// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { useGetExperiment } from '@nemo/sdk/generated/platform/api';
import { Divider } from '@nvidia/foundations-react-core';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { type FC } from 'react';

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

  return (
    <div className="flex gap-8">
      <KVPair
        label="Agent Names"
        value={experiment?.agent_names?.join(', ') || undefined}
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
      <Divider orientation="vertical" className="grow-0 self-stretch" />
      <KVPair label="Avg Cost" value={avgCost} loading={isLoading} orientation="vertical" />
      <Divider orientation="vertical" className="grow-0 self-stretch" />
      <KVPair label="Avg Latency" value={avgLatency} loading={isLoading} orientation="vertical" />
    </div>
  );
};
