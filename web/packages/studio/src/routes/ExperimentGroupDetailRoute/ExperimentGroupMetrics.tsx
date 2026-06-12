// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { useGetExperimentGroup } from '@nemo/sdk/generated/platform/api';
import { Divider } from '@nvidia/foundations-react-core';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { type FC } from 'react';

interface ExperimentGroupMetricsProps {
  experimentGroupName: string;
}

export const ExperimentGroupMetrics: FC<ExperimentGroupMetricsProps> = ({
  experimentGroupName,
}) => {
  const workspace = useWorkspaceFromPath();
  const { data: group } = useGetExperimentGroup(workspace, experimentGroupName);

  return (
    <div className="flex gap-8">
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
