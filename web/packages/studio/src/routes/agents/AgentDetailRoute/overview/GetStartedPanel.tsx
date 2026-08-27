// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Card, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import {
  agentIntegrationPrompt,
  traceImportPrompt,
} from '@studio/routes/agents/AgentDetailRoute/overview/codingAgentPrompts';
import { GetStartedOption } from '@studio/routes/agents/AgentDetailRoute/overview/GetStartedOption';
import type { FC } from 'react';

interface GetStartedPanelProps {
  workspace: string;
  /** Named in the prompts so the coding agent knows which agent to wire up. */
  agentName?: string;
}

/**
 * What the overview shows before an agent reports anything: the two ways to connect it.
 *
 * Both paths are work the user does in their own repository, so each hands off a prompt for their
 * coding agent rather than trying to do it from Studio.
 */
export const GetStartedPanel: FC<GetStartedPanelProps> = ({ workspace, agentName }) => {
  const params = { workspace, agent: agentName, baseUrl: PLATFORM_BASE_URL };

  return (
    <Stack gap="4">
      <Text kind="title/md">Get started with agent optimization</Text>
      <Card>
        <Flex gap="density-2xl" align="center" padding="density-xl">
          <GetStartedOption
            heading="Begin with traces"
            description="Import observability data to generate insights and power dataset generation from traces, without altering agent code."
            actionLabel="Get coding agent prompt for importing traces"
            prompt={traceImportPrompt(params)}
          />
          <GetStartedOption
            heading="Integrate your agent"
            description="Integrate your agent to NeMo Platform via Fabric to power evaluations, auto optimization, and manage agent deployments."
            actionLabel="Get coding agent prompt for integrating your agent"
            prompt={agentIntegrationPrompt(params)}
          />
        </Flex>
      </Card>
    </Stack>
  );
};
