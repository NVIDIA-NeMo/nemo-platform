// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { EvalJobStatus } from '@studio/routes/agents/AgentSuggestionsRoute/types';

export const EVAL_STATUS_LABEL: Record<EvalJobStatus, string> = {
  queued: 'Queued',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
  unknown: 'Unknown',
};

export const EVAL_STATUS_COLOR: Record<EvalJobStatus, 'gray' | 'green' | 'red' | 'blue'> = {
  queued: 'gray',
  running: 'blue',
  completed: 'green',
  failed: 'red',
  cancelled: 'gray',
  unknown: 'gray',
};

export const SCOPE_AGENT = 'agent';
export const SCOPE_WORKSPACE = 'workspace';

export const SCOPE_OPTIONS = [
  { value: SCOPE_AGENT, label: 'Agent-specific' },
  { value: SCOPE_WORKSPACE, label: 'Workspace-wide' },
];

export const TYPE_OPTIONS = [
  { value: 'model_optimization', label: 'Model Optimization' },
  { value: 'guardrails', label: 'Guardrails' },
  { value: 'data_safety', label: 'Data Safety' },
  { value: 'new_model_scan', label: 'New Model' },
];

export const SEVERITY_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };

export const STALE_SUGGESTION_MS = 7 * 24 * 60 * 60 * 1000;

// Bundled sample eval config + dataset, vendored from
// plugins/nemo-agents/examples/react-agent/ so the optimizer's apply flow can
// stand up an eval pipeline without a pre-uploaded one. The eval invokes
// `nat eval` against the agent's running endpoint, so llms.llm is mostly
// unused — the worker LLM is the deployed agent's. llms.judge_llm IS used
// for scoring and must be available in the workspace's inference gateway;
// missing judge fails the eval loudly, which is the correct signal.
export const SAMPLE_EVAL_CONFIG_PATH = 'react-eval.yml';
export const SAMPLE_EVAL_DATA_PATH = 'react-eval-data.json';

export const EVAL_CONFIG_FILESET_HELP_TEXT =
  'A valid evaluation config is a NAT evaluation YAML file with a .yml or .yaml extension. Upload one to a fileset, then select that file here.';

export const SAMPLE_EVAL_YAML = `# react-eval.yml — bundled sample seeded by the optimizer apply flow.
#
# Evaluates against the deployed agent endpoint. The judge LLM scores answers
# and must be available in the workspace.

llms:
  llm:
    _type: openai
    model_name: nvidia-nemotron-3-nano-30b-a3b
    temperature: 0.0
    max_tokens: 1024

  judge_llm:
    _type: openai
    model_name: nvidia-nemotron-3-super-120b-a12b
    temperature: 0.0
    max_tokens: 1024

eval:
  general:
    max_concurrency: 4
    output_dir: eval/agent
    dataset:
      _type: json
      file_path: ${SAMPLE_EVAL_DATA_PATH}
  evaluators:
    accuracy:
      _type: tunable_rag_evaluator
      llm_name: judge_llm
      default_scoring: true
      default_score_weights:
        coverage: 0.5
        correctness: 0.3
        relevance: 0.2
      judge_llm_prompt: >
        You are an evaluator. Score whether the generated answer correctly
        addresses the question compared to the expected answer description.
        Rules:
        - Score is a float between 0.0 and 1.0.
        - 1.0 means the answer fully satisfies the expected answer criteria.
        - Provide a 1-2 sentence reasoning.
`;

export const SAMPLE_EVAL_DATA_JSON = JSON.stringify(
  [
    {
      id: 1,
      question: 'Who invented the telephone, and what is the current time?',
      answer:
        'Answer must mention Alexander Graham Bell as the inventor of the telephone and include the current time',
    },
    {
      id: 2,
      question: 'What is the capital of France, and what day of the week is it today?',
      answer:
        'Answer must state that the capital of France is Paris and include the current day of the week',
    },
    {
      id: 3,
      question: "When was the theory of general relativity published, and what is today's date?",
      answer:
        "Answer must mention 1915 as the year general relativity was published and include today's date",
    },
  ],
  null,
  2
);
