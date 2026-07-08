// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { http, HttpResponse } from 'msw';

// Realistic fixtures for the public/sample-agents/* static assets. The create
// flow parses the returned agent.yml, so these must be valid NAT config YAML —
// not a '{}' stub.
const PHISHING_AGENT_YAML = `functions:
  email_phishing_analyzer:
    _type: email_phishing_analyzer
    llm: llm
llms:
  llm:
    _type: openai
    api_key: not-used
    model_name: \${NEMO_DEFAULT_MODEL}
    temperature: 0.0
workflow:
  _type: tool_calling_agent
  tool_names: [email_phishing_analyzer]
  llm_name: llm
`;

const CALCULATOR_AGENT_YAML = `function_groups:
  calculator:
    _type: calculator
functions:
  current_datetime:
    _type: current_datetime
llms:
  llm:
    _type: openai
    api_key: not-used
    model_name: \${NEMO_DEFAULT_MODEL}
    temperature: 0.0
workflow:
  _type: react_agent
  tool_names: [calculator, current_datetime]
  llm_name: llm
  use_native_tool_calling: true
`;

const EVAL_YAML = `llms:
  judge_llm:
    _type: openai
    model_name: nvidia-nemotron-3-super-120b-a12b
eval:
  general:
    dataset:
      _type: csv
      file_path: smaller_test.csv
  evaluators:
    accuracy:
      _type: tunable_rag_evaluator
      llm_name: judge_llm
`;

/** Handlers for sample-agent static asset requests (paths relative to BASE_URL). */
export const sampleAgentsHandlers = [
  http.get(/\/sample-agents\/.+/, ({ request }) => {
    const path = new URL(request.url).pathname;
    if (path.endsWith('/agent.yml')) {
      const body = path.includes('/calculator/') ? CALCULATOR_AGENT_YAML : PHISHING_AGENT_YAML;
      return HttpResponse.text(body, { headers: { 'Content-Type': 'application/yaml' } });
    }
    if (path.endsWith('.yml')) {
      return HttpResponse.text(EVAL_YAML, { headers: { 'Content-Type': 'application/yaml' } });
    }
    if (path.endsWith('.csv')) {
      return HttpResponse.text('subject,body,label\nHi,benign body,benign\n', {
        headers: { 'Content-Type': 'text/csv' },
      });
    }
    return HttpResponse.text('[]', { headers: { 'Content-Type': 'application/json' } });
  }),
];
