// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ExperimentGroupResponse } from '@nemo/sdk/generated/platform/schema';
import { Card, Text } from '@nvidia/foundations-react-core';
import { Metric } from '@studio/routes/ExperimentRoute/Metric';
import { UpdatedAt } from '@studio/routes/ExperimentRoute/UpdatedAt';
import { getExperimentGroupDetailRoute } from '@studio/routes/utils';
import { type FC } from 'react';
import { useNavigate } from 'react-router-dom';

interface ExperimentGroupCardProps {
  group: ExperimentGroupResponse;
  workspace: string;
}

export const ExperimentGroupCard: FC<ExperimentGroupCardProps> = ({ group, workspace }) => {
  const navigate = useNavigate();

  return (
    <Card
      interactive
      attributes={{ CardContent: { className: 'flex flex-row items-center gap-6 p-6' } }}
      onClick={() => navigate(getExperimentGroupDetailRoute(workspace, group.name))}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          navigate(getExperimentGroupDetailRoute(workspace, group.name));
        } else if (e.key === ' ') {
          e.preventDefault();
          navigate(getExperimentGroupDetailRoute(workspace, group.name));
        }
      }}
    >
      {/* Main info */}
      <div className="flex flex-col items-start gap-2 flex-1">
        <Text kind="title/sm">{group.name}</Text>
        {group.description && (
          <Text kind="body/regular/sm" className="text-secondary">
            {group.description}
          </Text>
        )}
        <div className="flex items-center gap-4">
          {group.updated_at && <UpdatedAt datetime={group.updated_at} />}
        </div>
      </div>

      {/* Stats */}
      <div className="flex shrink-0 items-center gap-6">
        <Metric title="Experiments" value={String(group.experiment_count ?? 0)} />
      </div>
    </Card>
  );
};
