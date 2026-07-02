// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Capability, JsonSchema } from '../types';

/** Tool definition in the shape accepted by the Anthropic Messages API `tools` param. */
export interface AnthropicTool {
  readonly name: string;
  readonly description: string;
  readonly input_schema: JsonSchema;
}

/** Converts capabilities to Anthropic tool definitions. */
export const toAnthropicTools = (capabilities: readonly Capability[]): AnthropicTool[] =>
  capabilities.map((c) => ({
    name: c.name,
    description: c.description,
    input_schema: c.inputSchema,
  }));
