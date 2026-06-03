// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ThreadAssistantMessagePart } from '@assistant-ui/react';

type ClaudeCodeToolCallPart = Extract<ThreadAssistantMessagePart, { type: 'tool-call' }>;
export type ClaudeCodeToolArgs = ClaudeCodeToolCallPart['args'];
type ClaudeCodeToolArgValue = ClaudeCodeToolArgs[string];

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const toClaudeCodeToolArgValue = (value: unknown): ClaudeCodeToolArgValue | undefined => {
  if (value === null) return value;
  if (typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') return Number.isFinite(value) ? value : undefined;

  if (Array.isArray(value)) {
    return value
      .map(toClaudeCodeToolArgValue)
      .filter((item): item is ClaudeCodeToolArgValue => item !== undefined);
  }

  if (isRecord(value)) return toClaudeCodeToolArgs(value);

  return undefined;
};

export const toClaudeCodeToolArgs = (input: unknown): ClaudeCodeToolArgs => {
  if (!isRecord(input)) return {};

  const args: Record<string, ClaudeCodeToolArgValue> = {};
  for (const [key, value] of Object.entries(input)) {
    const nextValue = toClaudeCodeToolArgValue(value);
    if (nextValue !== undefined) args[key] = nextValue;
  }

  return args;
};

export const createClaudeCodeToolCallPart = ({
  input,
  toolCallId,
  toolName,
}: {
  input: unknown;
  toolCallId: string;
  toolName: string;
}): ThreadAssistantMessagePart => {
  const args = toClaudeCodeToolArgs(input);
  return {
    type: 'tool-call',
    toolCallId,
    toolName,
    args,
    argsText: JSON.stringify(args),
  };
};
