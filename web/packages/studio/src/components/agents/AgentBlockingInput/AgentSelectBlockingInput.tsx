// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { ControlledSelect } from '@nemo/common/src/components/form/ControlledSelect';
import { AgentBlockingInputFrame } from '@studio/components/agents/AgentBlockingInput/AgentBlockingInputFrame';
import { fetchAgentsForSelect } from '@studio/components/agents/AgentBlockingInput/agentQueries';
import type {
  AgentBlockingInputRequest,
  AgentBlockingInputStatus,
  AgentBlockingInputSubmission,
} from '@studio/components/agents/AgentBlockingInput/types';
import { getStringValue } from '@studio/components/agents/AgentBlockingInput/utils';
import { useQuery } from '@tanstack/react-query';
import { type FC, useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

const agentSelectSchema = z.object({
  agent: z.string().trim().min(1, 'Agent is required'),
});

type AgentSelectFormData = z.infer<typeof agentSelectSchema>;

interface AgentSelectBlockingInputProps {
  readonly input?: Record<string, unknown>;
  readonly onSkip?: () => Promise<void> | void;
  readonly onSubmit: (submission: AgentBlockingInputSubmission) => Promise<void> | void;
  readonly request: AgentBlockingInputRequest;
  readonly status?: AgentBlockingInputStatus;
  readonly workspace: string;
}

export const AgentSelectBlockingInput: FC<AgentSelectBlockingInputProps> = ({
  input = {},
  onSkip,
  onSubmit,
  request,
  status = 'pending',
  workspace,
}) => {
  const defaultAgent =
    getStringValue(input, 'default_agent') ?? getStringValue(input, 'agent') ?? '';
  const isSubmitting = status === 'submitting';
  const { control, handleSubmit } = useForm<AgentSelectFormData>({
    defaultValues: { agent: defaultAgent },
    resolver: zodResolver(agentSelectSchema),
    disabled: isSubmitting,
  });
  const { data: agents = [], isLoading } = useQuery({
    queryKey: ['agent-blocking-input', 'agents', workspace],
    queryFn: ({ signal }) => fetchAgentsForSelect(workspace, signal),
    enabled: !!workspace,
  });
  const items = useMemo(() => {
    const agentItems = agents.flatMap((agent) =>
      agent.name ? [{ value: agent.name, children: agent.name }] : []
    );
    if (defaultAgent && !agentItems.some((item) => item.value === defaultAgent)) {
      return [{ value: defaultAgent, children: defaultAgent }, ...agentItems];
    }
    return agentItems;
  }, [agents, defaultAgent]);

  const submit = handleSubmit((data) => {
    void onSubmit({
      displayText: `Selected agent: ${data.agent}`,
      value: { agent: data.agent },
    });
  });

  return (
    <AgentBlockingInputFrame
      isSubmitting={isSubmitting}
      onSkip={onSkip}
      onSubmit={submit}
      request={request}
      submitDisabled={!items.length}
      submitLabel="Select agent"
    >
      <ControlledSelect
        useControllerProps={{
          control,
          name: 'agent',
        }}
        loading={isLoading}
        items={items}
        formFieldProps={{
          slotLabel: 'Agent',
        }}
      />
    </AgentBlockingInputFrame>
  );
};
