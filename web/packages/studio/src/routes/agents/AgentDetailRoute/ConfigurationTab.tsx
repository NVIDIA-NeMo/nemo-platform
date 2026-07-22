// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { isDefined } from '@nemo/common/src/utils/list';
import type { Agent } from '@nemo/sdk/generated/agents/schema/Agent';
import { Stack } from '@nvidia/foundations-react-core';
import type { AgentConfig } from '@studio/components/dataViews/AgentsDataView';
import { getAgentModelNames } from '@studio/components/dataViews/AgentsDataView/utils';
import { DetailPanel } from '@studio/routes/agents/AgentDetailRoute/overview/DetailPanel';
import type { FC } from 'react';

interface ConfigurationTabProps {
  workspace: string;
  agentName?: string;
  agent?: Agent;
}

/** Read-only view of the agent's configuration metadata. */
export const ConfigurationTab: FC<ConfigurationTabProps> = ({ workspace, agentName, agent }) => {
  const models = getAgentModelNames(agent?.config as AgentConfig | undefined);

  return (
    <DetailPanel title="Configuration">
      <Stack gap="2">
        <KVPair label="Name" value={agent?.name ?? agentName} />
        <KVPair label="Workspace" value={agent?.workspace ?? workspace} />
        {isDefined(agent?.description) && (
          <KVPair label="Description" value={agent.description || '-'} />
        )}
        {models.length > 0 && <KVPair label="Model" value={models.join(', ')} />}
        {isDefined(agent?.config_format) && (
          <KVPair label="Config Format" value={agent.config_format} />
        )}
      </Stack>
    </DetailPanel>
  );
};
