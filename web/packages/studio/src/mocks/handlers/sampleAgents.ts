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

const SECURITY_AGENT_YAML = `functions:
  analyze_email:
    _type: analyze_email
    llm: llm
  extract_iocs:
    _type: extract_iocs
llms:
  llm:
    _type: openai
    api_key: not-used
    model_name: default/nvidia-nemotron-3-nano-30b-a3b
    temperature: 0.0
    max_tokens: 4096
workflow:
  _type: tool_calling_agent
  tool_names: [analyze_email, extract_iocs]
  llm_name: llm
`;

/** Handlers for sample-agent static asset requests (paths relative to BASE_URL). */
export const sampleAgentsHandlers = [
  http.get(/\/sample-agents\/.+/, ({ request }) => {
    const path = new URL(request.url).pathname;
    if (path.endsWith('/agent.yml')) {
      const body = path.includes('/email-security-analyst/')
        ? SECURITY_AGENT_YAML
        : PHISHING_AGENT_YAML;
      return HttpResponse.text(body, { headers: { 'Content-Type': 'application/yaml' } });
    }
    return HttpResponse.text('[]', { headers: { 'Content-Type': 'application/json' } });
  }),
];
