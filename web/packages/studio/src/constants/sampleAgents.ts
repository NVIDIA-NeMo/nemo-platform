// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { z } from 'zod';

// Registry of canned example agents. Each entry references curated static assets
// under public/sample-agents/<dir>/ by path (fetched on demand, never bundled) —
// mirroring src/constants/sampleDatasets.ts. Used by both the Create Example Agent
// modal (fetch + parse agent.yml, inject model, POST) and the Run Evaluation modal
// (seed eval.yml + dataset into the {agent}-eval fileset).
//
// INVARIANT: an entry whose agent.yml uses a custom NAT `_type` requires that
// tool's Python package to be installed in the deploy venv, or the deployment
// fails at startup. Current mappings:
//   _type: calculator              -> plugins/nemo-agents/examples/calculator-agent
//   _type: email_phishing_analyzer -> plugins/nemo-agents/examples/email-phishing-analyzer
export interface SampleAgent {
  /** Stable key; also the dropdown value and label. */
  key: string;
  label: string;
  description: string;
  /** Prefix for generated agent names; drives onboarding detection. */
  namePrefix: string;
  /** Public path to the NAT workflow config (parsed + model-injected at create). */
  agentConfigPath: string;
  /** Public path to the NAT eval config (seeded verbatim into the eval fileset
   *  under its basename). */
  evalConfigPath: string;
  /** Public path to the eval dataset, seeded alongside the eval config under its
   *  basename. That basename MUST equal the eval config's dataset file_path. */
  evalDataPath: string;
}

export const SAMPLE_AGENTS: SampleAgent[] = [
  {
    key: 'calculator',
    label: 'calculator',
    description: 'A ReAct agent with a calculator and datetime tool.',
    namePrefix: 'calculator-demo-agent',
    agentConfigPath: 'sample-agents/calculator/agent.yml',
    evalConfigPath: 'sample-agents/calculator/eval.yml',
    evalDataPath: 'sample-agents/calculator/calculator-eval-data.json',
  },
  {
    key: 'email_phishing_analyzer',
    label: 'email_phishing_analyzer',
    description: 'A ReAct agent that inspects an email body for phishing signals.',
    namePrefix: 'email-phishing-demo-agent',
    agentConfigPath: 'sample-agents/email-phishing-analyzer/agent.yml',
    evalConfigPath: 'sample-agents/email-phishing-analyzer/eval.yml',
    evalDataPath: 'sample-agents/email-phishing-analyzer/smaller_test.csv',
  },
];

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
 * undefined for agents not created from an example. Used to auto-select the
 * matching eval config.
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
