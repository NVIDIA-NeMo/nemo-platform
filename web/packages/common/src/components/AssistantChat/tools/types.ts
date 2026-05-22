// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ToolCallMessagePartProps } from '@assistant-ui/react';
import type { ChatCompletionTool } from 'openai/resources/index.mjs';
import type { ComponentType } from 'react';

export interface ToolExecutionContext {
  readonly signal: AbortSignal;
}

export type ToolExecutionOutcome =
  | { readonly ok: true; readonly result: unknown }
  | { readonly ok: false; readonly error: string };

export interface StudioTool<TArgs = Record<string, unknown>> {
  readonly name: string;
  readonly label: string;
  readonly description: string;
  readonly parameters: ChatCompletionTool['function']['parameters'];
  readonly execute: (args: TArgs, ctx: ToolExecutionContext) => Promise<ToolExecutionOutcome>;
  readonly Render?: ComponentType<ToolCallMessagePartProps>;
}

export type StudioToolRegistry = ReadonlyArray<StudioTool>;
export type AssistantChatTool = StudioTool | ChatCompletionTool;

export const isStudioTool = (tool: AssistantChatTool): tool is StudioTool =>
  'execute' in tool && typeof tool.execute === 'function';

export const getAssistantChatToolName = (tool: AssistantChatTool): string =>
  isStudioTool(tool) ? tool.name : tool.function.name;

export const toOpenAITool = (tool: AssistantChatTool): ChatCompletionTool =>
  isStudioTool(tool)
    ? {
        type: 'function',
        function: {
          name: tool.name,
          description: tool.description,
          parameters: tool.parameters,
        },
      }
    : tool;
