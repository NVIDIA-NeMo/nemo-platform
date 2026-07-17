// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useToast } from '@nemo/common/src/providers/toast/useToast';
import {
  getAgentsExternalAgentReachabilityQueryKey,
  getAgentsGetAgentQueryKey,
  useAgentsExternalAgentReachability,
  useAgentsRefreshExternalAgent,
} from '@nemo/sdk/generated/agents/api';
import { Button, Flex, StatusIndicator, Text } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { useQueryClient } from '@tanstack/react-query';
import { RotateCw } from 'lucide-react';
import type { FC } from 'react';

const REACHABILITY_POLL_MS = 30_000;

interface ExternalAgentStatusProps {
  workspace: string;
  agentName: string;
}

/**
 * Reachability badge + card-refresh for an external agent. The card is captured
 * once at registration, so refresh re-fetches it; the badge polls a lightweight
 * liveness probe so a dead endpoint isn't invisible until you try to chat.
 */
export const ExternalAgentStatus: FC<ExternalAgentStatusProps> = ({ workspace, agentName }) => {
  const toast = useToast();
  const queryClient = useQueryClient();

  const { data: reachability, isLoading } = useAgentsExternalAgentReachability(
    workspace,
    agentName,
    { query: { enabled: !!agentName, refetchInterval: REACHABILITY_POLL_MS } }
  );

  const { mutate: refresh, isPending } = useAgentsRefreshExternalAgent({
    mutation: {
      onSuccess: () => {
        toast.success('Agent card refreshed');
        void queryClient.invalidateQueries({
          queryKey: getAgentsGetAgentQueryKey(workspace, agentName),
        });
        void queryClient.invalidateQueries({
          queryKey: getAgentsExternalAgentReachabilityQueryKey(workspace, agentName),
        });
      },
      onError: (error) =>
        toast.error(getErrorMessage(error as Error, 'Failed to refresh agent card')),
    },
  });

  const status = isLoading ? 'checking' : reachability?.reachable ? 'reachable' : 'unreachable';
  const label =
    status === 'checking' ? 'Checking…' : status === 'reachable' ? 'Reachable' : 'Unreachable';
  const color = status === 'reachable' ? 'green' : status === 'unreachable' ? 'red' : 'yellow';

  return (
    <Flex gap="2" align="center">
      <StatusIndicator color={color} size="small" />
      <Text kind="body/regular/sm" color="secondary">
        {label}
      </Text>
      <Button
        kind="tertiary"
        size="small"
        disabled={isPending}
        onClick={() => refresh({ workspace, name: agentName })}
      >
        <RotateCw className="size-3" /> {isPending ? 'Refreshing…' : 'Refresh card'}
      </Button>
    </Flex>
  );
};
