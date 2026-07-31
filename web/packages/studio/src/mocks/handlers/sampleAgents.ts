// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { http, HttpResponse } from 'msw';

// Realistic fixtures for the public/sample-agents/* static assets. The create
// flow parses the returned agent.yml, so these must be valid NAT config YAML —
// not a '{}' stub.
const SECURITY_AGENT_YAML = `functions:
  review_messages:
    _type: review_messages
    llm: llm
  triage_message:
    _type: triage_message
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
  tool_names: [review_messages, triage_message, extract_iocs]
  return_direct: [review_messages, triage_message, extract_iocs]
  llm_name: llm
`;

/** Handlers for sample-agent static asset requests (paths relative to BASE_URL). */
export const sampleAgentsHandlers = [
  http.get(/\/sample-agents\/.+/, ({ request }) => {
    const path = new URL(request.url).pathname;
    if (path.endsWith('/agent.yml')) {
      return HttpResponse.text(SECURITY_AGENT_YAML, {
        headers: { 'Content-Type': 'application/yaml' },
      });
    }
    return HttpResponse.text('[]', { headers: { 'Content-Type': 'application/json' } });
  }),
];
