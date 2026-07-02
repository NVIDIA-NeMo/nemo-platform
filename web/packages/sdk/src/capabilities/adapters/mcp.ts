// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Capability, CapabilityContext, JsonSchema } from '../types';

/** Tool descriptor in the Model Context Protocol `tools/list` shape. */
export interface McpTool {
  readonly name: string;
  readonly description: string;
  readonly inputSchema: JsonSchema;
}

/** MCP `tools/call` result content (text-only). */
export interface McpCallResult {
  readonly content: Array<{ readonly type: 'text'; readonly text: string }>;
  readonly isError?: boolean;
}

/** Converts capabilities to MCP tool descriptors (for `tools/list`). */
export const toMcpTools = (capabilities: readonly Capability[]): McpTool[] =>
  capabilities.map((c) => ({
    name: c.name,
    description: c.description,
    inputSchema: c.inputSchema,
  }));

/**
 * Dispatches an MCP `tools/call` to the matching capability and returns an
 * MCP-shaped result. Wire this into an MCP server's call handler; pair it with
 * {@link toMcpTools} for the list handler.
 */
export const callMcpTool = async (
  capabilities: readonly Capability[],
  ctx: CapabilityContext,
  name: string,
  args: unknown
): Promise<McpCallResult> => {
  const capability = capabilities.find((c) => c.name === name);
  if (!capability) {
    return { content: [{ type: 'text', text: `Unknown tool: ${name}` }], isError: true };
  }
  const result = await capability.execute(args, ctx);
  return {
    content: [{ type: 'text', text: result.content }],
    isError: result.isError,
  };
};
