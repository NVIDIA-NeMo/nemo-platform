// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { useGetExperimentGroup } from '@nemo/sdk/generated/platform/api';
import { Divider } from '@nvidia/foundations-react-core';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useAllGroupExperiments } from '@studio/routes/ExperimentGroupDetailRoute/useAllGroupExperiments';
import { type FC, useMemo } from 'react';

interface ExperimentGroupMetricsProps {
  experimentGroupName: string;
}

export const ExperimentGroupMetrics: FC<ExperimentGroupMetricsProps> = ({
  experimentGroupName,
}) => {
  const workspace = useWorkspaceFromPath();
  const { data: group } = useGetExperimentGroup(workspace, experimentGroupName);
  const { experiments, isFetching } = useAllGroupExperiments(workspace, group?.id ?? '');

  const agentNames = useMemo(
    () => [...new Set(experiments.map((e) => e.agent_name).filter(Boolean))].join(', '),
    [experiments]
  );

  const datasetNames = useMemo(
    () => [...new Set(experiments.map((e) => e.dataset_name).filter(Boolean))].join(', '),
    [experiments]
  );

  return (
    <div className="flex gap-8">
      <KVPair
        label="Agent"
        value={agentNames || undefined}
        loading={isFetching}
        orientation="vertical"
      />
      <Divider orientation="vertical" className="grow-0 self-stretch" />
      <KVPair
        label="Dataset"
        value={datasetNames || undefined}
        loading={isFetching}
        orientation="vertical"
      />
      <Divider orientation="vertical" className="grow-0 self-stretch" />
      <KVPair
        label="Created"
        value={group?.created_at ? <RelativeTime datetime={group.created_at} /> : undefined}
        orientation="vertical"
      />
      <Divider orientation="vertical" className="grow-0 self-stretch" />
      <KVPair
        label="Updated"
        value={group?.updated_at ? <RelativeTime datetime={group.updated_at} /> : undefined}
        orientation="vertical"
      />
    </div>
  );
};
