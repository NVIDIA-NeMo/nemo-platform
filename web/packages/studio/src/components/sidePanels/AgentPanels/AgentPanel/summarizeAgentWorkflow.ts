// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AgentConfig } from '@studio/components/dataViews/AgentsDataView';

export interface WorkflowToolNode {
  name: string;
  type: string;
  /** True when the workflow's tool_names wires this function in as a tool. */
  wired: boolean;
}

export interface AgentWorkflowSummary {
  workflowType?: string;
  llmName?: string;
  models: string[];
  tools: WorkflowToolNode[];
}

/**
 * Derives a display-friendly view of a NAT workflow config: the top-level
 * workflow type, its LLM/model, and the functions declared in the config —
 * flagging which are wired into the agent via `workflow.tool_names`. Purely a
 * read model over the stored config; it does not validate the NAT schema.
 */
export const summarizeAgentWorkflow = (config: AgentConfig | undefined): AgentWorkflowSummary => {
  const workflow = config?.workflow;
  const wiredNames = new Set(workflow?.tool_names ?? []);

  const models = Object.values(config?.llms ?? {})
    .map((llm) => llm?.model_name)
    .filter((m): m is string => !!m);

  const tools: WorkflowToolNode[] = Object.entries(config?.functions ?? {}).map(([name, fn]) => ({
    name,
    type: fn?._type ?? 'unknown',
    wired: wiredNames.has(name),
  }));

  return {
    workflowType: workflow?._type,
    llmName: workflow?.llm_name,
    models: [...new Set(models)],
    tools,
  };
};
