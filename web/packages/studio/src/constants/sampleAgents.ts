// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { z } from 'zod';

// Registry of canned example agents. Each entry references curated static assets
// under public/sample-agents/<dir>/ by path (fetched on demand, never bundled) —
// mirroring src/constants/sampleDatasets.ts. Used by both the Create Example Agent
// modal (fetch + parse agent.yml, inject model, POST). Samples with an
// evalConfigPath also appear in the Run Evaluation modal.
//
// INVARIANT: an entry whose agent.yml uses a custom NAT `_type` requires that
// tool's Python package to be installed in the deploy venv, or the deployment
// fails at startup. Current mappings:
//   _type: calculator              -> plugins/nemo-agents/examples/calculator-agent
//   _type: email_phishing_analyzer -> plugins/nemo-agents/examples/email-phishing-analyzer
//   _type: analyze_email           -> plugins/nemo-agents/examples/email-security-analyst
//   _type: extract_iocs            -> plugins/nemo-agents/examples/email-security-analyst
export interface SampleAgent {
  /** Stable key; also the dropdown value and label. */
  key: string;
  label: string;
  displayName: string;
  description: string;
  evalSummary: string;
  /** Prefix for generated agent names; drives onboarding detection. */
  namePrefix: string;
  /** Public path to the NAT workflow config (parsed + model-injected at create). */
  agentConfigPath: string;
  /** Public path to a reusable nemo-evaluator eval-config.json. Samples without
   *  one remain available for agent creation but not evaluation seeding. */
  evalConfigPath?: string;
  /** Public path to the dataset a dataset-driven eval-config scores over. Seeded
   *  into the run's fileset alongside the config so the sample is self-contained. */
  datasetPath?: string;
}

export const SAMPLE_AGENTS: SampleAgent[] = [
  {
    key: 'email_phishing_analyzer',
    label: 'email_phishing_analyzer',
    displayName: 'Email Phishing Analyzer',
    description:
      'A phishing classifier scored dataset-driven: one metric set over every row of a labeled email dataset.',
    evalSummary:
      'Dataset-driven: the agent produces an output for every row of a fixed dataset, and one metric set scores each output against its expected answer.',
    namePrefix: 'email-phishing',
    agentConfigPath: 'sample-agents/email-phishing-analyzer/agent.yml',
    evalConfigPath: 'sample-agents/email-phishing-analyzer/eval-config.json',
    datasetPath: 'sample-agents/email-phishing-analyzer/dataset.jsonl',
  },
  {
    key: 'email_security_analyst',
    label: 'email_security_analyst',
    displayName: 'Email Security Analyst',
    description:
      'A security analyst scored task-driven: varied input shapes — single messages, inbox batches, threads, headers, URLs — each with the metrics that fit it.',
    evalSummary:
      'Task-driven: the agent performs a set of distinct tasks, and each task carries its own metrics, so one suite can grade heterogeneous work.',
    namePrefix: 'email-security-analyst',
    agentConfigPath: 'sample-agents/email-security-analyst/agent.yml',
    evalConfigPath: 'sample-agents/email-security-analyst/eval-config.json',
  },
];

export type EvaluationSampleAgent = SampleAgent & { evalConfigPath: string };

export const EVALUATION_SAMPLE_AGENTS = SAMPLE_AGENTS.filter(
  (agent): agent is EvaluationSampleAgent => typeof agent.evalConfigPath === 'string'
);

export const DEFAULT_SAMPLE_AGENT_KEY = SAMPLE_AGENTS[0].key;

export const getSampleAgent = (key: string): SampleAgent =>
  SAMPLE_AGENTS.find((agent) => agent.key === key) ?? SAMPLE_AGENTS[0];

export const getEvaluationSampleAgent = (key: string): EvaluationSampleAgent =>
  EVALUATION_SAMPLE_AGENTS.find((agent) => agent.key === key) ?? EVALUATION_SAMPLE_AGENTS[0];

export const evaluationSampleAgentKeyForAgentName = (
  name: string | undefined
): string | undefined => {
  const key = sampleAgentKeyForAgentName(name);
  return EVALUATION_SAMPLE_AGENTS.some((agent) => agent.key === key) ? key : undefined;
};

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
