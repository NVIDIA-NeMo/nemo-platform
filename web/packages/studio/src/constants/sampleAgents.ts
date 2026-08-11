// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { z } from 'zod';

// Registry of canned example agents. Each entry references curated static assets
// under public/sample-agents/<dir>/ by path (fetched on demand, never bundled) —
// mirroring src/constants/sampleDatasets.ts. Used by the Create Example Agent
// modal (fetch + parse agent.yml, inject model, POST).
//
// Eval configs are a SEPARATE registry (EVAL_CONFIG_SAMPLES) on purpose: either
// paradigm can target any agent, so a config is not owned by an agent.
//
// INVARIANT: a sample's deployment depends on something being installed in the
// deploy venv/image, or it fails at startup. Two shapes:
//
// 1. NAT (`nat-workflow-v1`) entries whose agent.yml uses a custom `_type` need
//    that tool's Python package:
//      _type: calculator              -> plugins/nemo-agents/examples/calculator-agent
//      _type: email_phishing_analyzer -> plugins/nemo-agents/examples/email-phishing-analyzer
//
// 2. Fabric (`nemo-agents-spec-v1`) entries need each `mcp.servers.<n>.url`
//    console script on PATH, since Fabric spawns it as a stdio MCP child:
//      email-phishing-iocs -> plugins/nemo-agents/examples/nemo-agent-config/email-phishing-agent
//
// Each public/sample-agents/<dir>/agent.yml is an independent copy of the
// example's config; keep them in sync by hand.
export interface SampleAgent {
  key: string;
  displayName: string;
  description: string;
  /** Prefix for generated agent names; drives onboarding detection. */
  namePrefix: string;
  /** Public path to the NAT workflow config (parsed + model-injected at create). */
  agentConfigPath: string;
  /** Config format identifier sent to the create API. Defaults to
   *  `nat-workflow-v1` server-side when omitted; set to `nemo-agents-spec-v1`
   *  for Fabric-backed samples so the API validates them as Fabric, not NAT. */
  configFormat?: string;
}

export const SAMPLE_AGENTS: SampleAgent[] = [
  {
    key: 'email_phishing_agent',
    displayName: 'Email Phishing Analyzer (Fabric)',
    description:
      'A Fabric DeepAgents orchestrator that delegates the phishing verdict to a sub-agent and calls a deterministic extract_iocs tool, so each step is tunable in config and emits its own trace span.',
    namePrefix: 'email-phishing-agent',
    agentConfigPath: 'sample-agents/email-phishing-agent/agent.yml',
    configFormat: 'nemo-agents-spec-v1',
  },
];

export interface EvalConfigSample {
  key: string;
  displayName: string;
  description: string;
  /** Public path to a reusable nemo-evaluator eval config. */
  configPath: string;
  /** Public path to the dataset a dataset-driven config scores over. Seeded into
   *  the run's fileset alongside the config so the sample is self-contained. */
  datasetPath?: string;
  /** Public path to a README seeded beside the config, explaining what the suite
   *  measures. Best-effort: a fetch failure does not block the submission. */
  readmePath?: string;
}

export const EVAL_CONFIG_SAMPLES: EvalConfigSample[] = [
  {
    key: 'task_driven',
    displayName: 'Task-Driven',
    description:
      'Inputs are varied tasks, each with its own metrics, so one suite can grade different kinds of work.',
    configPath: 'sample-agents/email-security-analyst/eval-config.task-driven.json',
    readmePath: 'sample-agents/email-security-analyst/eval-config.task-driven.README.md',
  },
  {
    key: 'dataset_driven',
    displayName: 'Dataset-Driven',
    description:
      'Inputs are rows in a dataset, each with an ideal response, scored by a common metric set.',
    configPath: 'sample-agents/email-security-analyst/eval-config.dataset-driven.json',
    datasetPath: 'sample-agents/email-security-analyst/dataset.jsonl',
    readmePath: 'sample-agents/email-security-analyst/eval-config.dataset-driven.README.md',
  },
];

export const DEFAULT_EVAL_CONFIG_KEY = EVAL_CONFIG_SAMPLES[0].key;

export const getEvalConfigSample = (key: string): EvalConfigSample =>
  EVAL_CONFIG_SAMPLES.find((sample) => sample.key === key) ?? EVAL_CONFIG_SAMPLES[0];

export const DEFAULT_SAMPLE_AGENT_KEY = SAMPLE_AGENTS[0].key;

export const getSampleAgent = (key: string): SampleAgent =>
  SAMPLE_AGENTS.find((agent) => agent.key === key) ?? SAMPLE_AGENTS[0];

export const buildSampleAgentName = (namePrefix: string): string =>
  `${namePrefix}-${Math.random().toString(36).slice(2, 8)}`;

export const isSampleAgentName = (name: string): boolean =>
  SAMPLE_AGENTS.some((agent) => name.startsWith(`${agent.namePrefix}-`));

/**
 * Infer which sample-agent example a deployed agent came from by matching its
 * generated name (`${namePrefix}-<suffix>`). Returns the example key, or
 * undefined for agents not created from an example.
 *
 * Robustness: requires the `${namePrefix}-` separator (so a prefix only matches
 * a real name boundary, not a partial token) and picks the LONGEST matching
 * prefix — so when one prefix is a substring of another (e.g. "test-" vs
 * "test-agent-"), the most specific wins deterministically.
 */
export const sampleAgentKeyForAgentName = (name: string | undefined): string | undefined => {
  if (!name) return undefined;
  return SAMPLE_AGENTS.filter((agent) => name.startsWith(`${agent.namePrefix}-`)).sort(
    (a, b) => b.namePrefix.length - a.namePrefix.length
  )[0]?.key;
};

export const sampleAgentFormSchema = z.object({
  exampleKey: z.string().min(1, 'Example is required'),
  modelName: z.string().min(1, 'Model is required'),
});
