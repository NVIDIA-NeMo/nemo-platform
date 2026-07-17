// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Agent } from '@nemo/sdk/generated/agents/schema/Agent';
import { Accordion, Badge, Block, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import type { AgentConfig } from '@studio/components/dataViews/AgentsDataView';
import { redactSecrets } from '@studio/components/sidePanels/AgentPanels/AgentPanel/redactSecrets';
import { summarizeAgentCard } from '@studio/components/sidePanels/AgentPanels/AgentPanel/summarizeAgentCard';
import { summarizeAgentWorkflow } from '@studio/components/sidePanels/AgentPanels/AgentPanel/summarizeAgentWorkflow';
import { isExternalAgent } from '@studio/util/agents';
import { Globe, Workflow, Wrench } from 'lucide-react';
import type { FC } from 'react';
import YAML from 'yaml';

interface AgentWorkflowContentProps {
  agent?: Agent;
}

export const AgentWorkflowContent: FC<AgentWorkflowContentProps> = ({ agent }) => {
  if (agent && isExternalAgent(agent)) {
    return <ExternalAgentWorkflow agent={agent} />;
  }

  const config = agent?.config as AgentConfig | undefined;
  const summary = summarizeAgentWorkflow(config);

  if (!config || (!summary.workflowType && summary.tools.length === 0)) {
    return (
      <Block padding="4">
        <Text color="secondary">This agent has no workflow config to visualize.</Text>
      </Block>
    );
  }

  let yamlText = '';
  try {
    yamlText = YAML.stringify(redactSecrets(config));
  } catch {
    yamlText = 'Unable to render config as YAML.';
  }

  const wiredTools = summary.tools.filter((t) => t.wired);
  const unwiredTools = summary.tools.filter((t) => !t.wired);

  return (
    <Stack className="overflow-auto" gap="4">
      <Block padding="4">
        <Stack gap="4">
          <Flex align="center" gap="2">
            <Workflow className="size-4 text-brand" />
            <Text kind="body/semibold/md">{summary.workflowType ?? 'workflow'}</Text>
            {summary.models.map((model) => (
              <Badge key={model} kind="outline">
                {model}
              </Badge>
            ))}
          </Flex>

          <Stack gap="2" align="center">
            <WorkflowNode label={summary.workflowType ?? 'workflow'} sub={summary.llmName} root />
            {wiredTools.length > 0 && (
              <>
                <div className="h-4 w-px bg-base" />
                <Flex gap="2" wrap="wrap" className="justify-center">
                  {wiredTools.map((tool) => (
                    <WorkflowNode key={tool.name} label={tool.name} sub={tool.type} />
                  ))}
                </Flex>
              </>
            )}
          </Stack>

          {unwiredTools.length > 0 && (
            <Text kind="body/regular/xs" color="secondary">
              Declared but not wired as tools: {unwiredTools.map((t) => t.name).join(', ')}
            </Text>
          )}
        </Stack>
      </Block>

      <Accordion
        multiple
        className="w-full border-t border-base"
        items={[
          {
            chevronPosition: 'start',
            value: 'config',
            slotTrigger: <Text kind="body/semibold/sm">Workflow config (YAML)</Text>,
            slotContent: (
              <Block>
                <pre className="font-mono text-xs whitespace-pre-wrap break-all max-h-96 overflow-auto bg-surface-subtle p-density-lg rounded leading-relaxed">
                  {yamlText}
                </pre>
              </Block>
            ),
          },
        ]}
      />
    </Stack>
  );
};

interface WorkflowNodeProps {
  label: string;
  sub?: string;
  root?: boolean;
}

const WorkflowNode: FC<WorkflowNodeProps> = ({ label, sub, root }) => (
  <Flex
    align="center"
    gap="2"
    className={`rounded-md border px-3 py-2 ${
      root ? 'border-brand bg-surface-subtle' : 'border-base'
    }`}
  >
    {!root && <Wrench className="size-3 text-subtle" />}
    <Stack gap="0">
      <Text kind="body/semibold/sm">{label}</Text>
      {sub && (
        <Text kind="body/regular/xs" color="secondary">
          {sub}
        </Text>
      )}
    </Stack>
  </Flex>
);

const ExternalAgentWorkflow: FC<{ agent: Agent }> = ({ agent }) => {
  const summary = summarizeAgentCard(agent.card);

  return (
    <Stack className="overflow-auto" gap="4">
      <Block padding="4">
        <Stack gap="4">
          <Flex align="center" gap="2">
            <Globe className="size-4 text-brand" />
            <Text kind="body/semibold/md">{summary.name ?? agent.name}</Text>
            <Badge kind="outline">External</Badge>
          </Flex>
          {agent.endpoint && (
            <Text kind="body/regular/xs" color="secondary" className="break-all">
              {agent.endpoint}
            </Text>
          )}

          {summary.skills.length > 0 ? (
            <Stack gap="2" align="center">
              <WorkflowNode label={summary.name ?? agent.name ?? 'agent'} root />
              <div className="h-4 w-px bg-base" />
              <Flex gap="2" wrap="wrap" className="justify-center">
                {summary.skills.map((skill) => (
                  <WorkflowNode key={skill.id} label={skill.name} sub={skill.description} />
                ))}
              </Flex>
            </Stack>
          ) : (
            <Text color="secondary">
              The agent card exposed no skills. This agent runs outside NeMo Platform.
            </Text>
          )}
        </Stack>
      </Block>

      <Accordion
        multiple
        className="w-full border-t border-base"
        items={[
          {
            chevronPosition: 'start',
            value: 'card',
            slotTrigger: <Text kind="body/semibold/sm">Agent card (JSON)</Text>,
            slotContent: (
              <Block>
                <pre className="font-mono text-xs whitespace-pre-wrap break-all max-h-96 overflow-auto bg-surface-subtle p-density-lg rounded leading-relaxed">
                  {JSON.stringify(redactSecrets(agent.card ?? {}), null, 2)}
                </pre>
              </Block>
            ),
          },
        ]}
      />
    </Stack>
  );
};
