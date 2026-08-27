// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

interface CodingAgentPromptParams {
  workspace: string;
  /** The agent this overview is for. Omitted when the agent has not loaded yet. */
  agent?: string;
  /** Origin the coding agent should point the platform CLI and SDK at. */
  baseUrl: string;
}

const agentLine = (agent?: string): string =>
  agent ? `The agent is named "${agent}".` : 'Use the agent in the current repository.';

/**
 * Prompts the user hands to a coding agent (Claude Code, Cursor, Codex) working in their own
 * repository. They name the NeMo skill that owns each path rather than restating its steps, so the
 * instructions stay correct as the skills change.
 */
export const traceImportPrompt = ({ workspace, agent, baseUrl }: CodingAgentPromptParams): string =>
  [
    `Send my agent's telemetry to NeMo Intake so I can see traces, insights, and generate datasets from real runs.`,
    agentLine(agent),
    ``,
    `Install the NeMo skills into this coding agent with \`nemo skills install --agent <your coding agent>\`, then read the nemo-intake skill and follow it step by step.`,
    ``,
    `Target: NMP_BASE_URL=${baseUrl}, WORKSPACE=${workspace}.`,
    ``,
    `Instrument the agent where it already emits telemetry — do not rewrite the agent. Pick the ingest format that fits what it emits (OTLP, chat completions, or ATIF), then run the agent once and verify the traces landed by querying Intake for this workspace.`,
  ].join('\n');

export const agentIntegrationPrompt = ({
  workspace,
  agent,
  baseUrl,
}: CodingAgentPromptParams): string =>
  [
    `Integrate my agent with NeMo Platform so I can evaluate it, optimize it, and manage its deployments from Studio.`,
    agentLine(agent),
    ``,
    `Install the NeMo skills into this coding agent with \`nemo skills install --agent <your coding agent>\`, then read the nemo-agent-config and nemo-build-agent skills and follow them step by step.`,
    ``,
    `Target: NMP_BASE_URL=${baseUrl}, WORKSPACE=${workspace}.`,
    ``,
    `Write the Fabric (nemo-agents-spec-v1) config for the agent, register it in this workspace, deploy it, and verify the deployment is healthy by invoking it once.`,
  ].join('\n');
