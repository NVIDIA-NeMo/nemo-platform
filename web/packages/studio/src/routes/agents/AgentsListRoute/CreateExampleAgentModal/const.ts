// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { z } from 'zod';

export const EXAMPLE_AGENT_DESCRIPTION = 'A ReAct agent with a calculator and datetime tool.';

export const EXAMPLE_AGENT_NAME_PREFIX = 'calculator-demo-agent';

export const buildExampleAgentName = (): string =>
  `${EXAMPLE_AGENT_NAME_PREFIX}-${Math.random().toString(36).slice(2, 8)}`;

export const isExampleAgentName = (name: string): boolean =>
  name.startsWith(EXAMPLE_AGENT_NAME_PREFIX);

// model_name is concrete: the service doesn't resolve ${NEMO_DEFAULT_MODEL} (only the CLI does).
export const buildExampleAgentConfig = (modelName: string): Record<string, unknown> => ({
  function_groups: {
    calculator: { _type: 'calculator' },
  },
  functions: {
    current_datetime: { _type: 'current_datetime' },
  },
  llms: {
    llm: {
      _type: 'openai',
      api_key: 'not-used', // platform overrides at deploy time
      model_name: modelName,
      temperature: 0,
    },
  },
  workflow: {
    _type: 'react_agent',
    tool_names: ['calculator', 'current_datetime'],
    llm_name: 'llm',
    verbose: false,
    parse_agent_response_max_retries: 3,
    use_native_tool_calling: true,
  },
});

export const exampleAgentFormSchema = z.object({
  modelName: z.string().min(1, 'Model is required'),
});
