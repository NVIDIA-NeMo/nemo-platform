// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Capability, JsonSchema } from '../types';

/** Tool definition in the OpenAI chat-completions `tools` (function-calling) shape. */
export interface OpenAITool {
  readonly type: 'function';
  readonly function: {
    readonly name: string;
    readonly description: string;
    readonly parameters: JsonSchema;
  };
}

/** Converts capabilities to OpenAI function-calling tool definitions. */
export const toOpenAITools = (capabilities: readonly Capability[]): OpenAITool[] =>
  capabilities.map((c) => ({
    type: 'function',
    function: {
      name: c.name,
      description: c.description,
      parameters: c.inputSchema,
    },
  }));
