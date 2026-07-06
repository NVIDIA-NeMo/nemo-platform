// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { z } from 'zod';

export const EXAMPLE_AGENT_DESCRIPTION =
  'A ReAct agent that classifies an email body as "phishing" or "benign".';

export const EXAMPLE_AGENT_NAME_PREFIX = 'email-phishing-analyzer';

// The prompt template for the email_phishing_analyzer tool. {body} is replaced
// with the email text at invoke time. Kept in sync with email-phishing-agent.yml.
const PHISHING_PROMPT = `Examine the following email content and determine if it exhibits signs of malicious intent. Look for any
suspicious signals that may indicate phishing, such as requests for personal information or suspicious tone.

Email content:
{body}

Return your findings as a JSON object with these fields:

- is_likely_phishing: (boolean) true if phishing is suspected
- explanation: (string) detailed explanation of your reasoning
`;

export const buildExampleAgentName = (): string =>
  `${EXAMPLE_AGENT_NAME_PREFIX}-${Math.random().toString(36).slice(2, 8)}`;

export const isExampleAgentName = (name: string): boolean =>
  name.startsWith(EXAMPLE_AGENT_NAME_PREFIX);

// model_name is concrete: the service doesn't resolve ${NEMO_DEFAULT_MODEL} (only the CLI does).
// The `email_phishing_analyzer` tool type is registered by the
// nemo-agents-example-email-phishing package baked into the agentic-base image.
export const buildExampleAgentConfig = (modelName: string): Record<string, unknown> => ({
  functions: {
    email_phishing_analyzer: {
      _type: 'email_phishing_analyzer',
      llm: 'llm',
      prompt: PHISHING_PROMPT,
    },
  },
  llms: {
    llm: {
      _type: 'openai',
      api_key: 'not-used', // platform overrides at deploy time
      model_name: modelName,
      temperature: 0,
      max_tokens: 512,
    },
  },
  workflow: {
    _type: 'react_agent',
    tool_names: ['email_phishing_analyzer'],
    llm_name: 'llm',
    verbose: false,
    parse_agent_response_max_retries: 3,
    use_native_tool_calling: true,
    additional_instructions:
      'The final response should indicate that the email is either "phishing" or "benign".',
  },
});

export const exampleAgentFormSchema = z.object({
  modelName: z.string().min(1, 'Model is required'),
});
