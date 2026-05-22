// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type {
  AppendMessage,
  MessageStatus,
  TextMessagePart,
  ThreadMessageLike,
} from '@assistant-ui/react';
import type {
  ChatCompletionAssistantMessageParam,
  ChatCompletionMessageParam,
  ChatCompletionMessageToolCall,
  ChatCompletionToolMessageParam,
} from 'openai/resources/index.mjs';

export interface ToolCallContentPart {
  readonly type: 'tool-call';
  readonly toolCallId?: string;
  readonly toolName: string;
  readonly argsText?: string;
  readonly args?: Record<string, unknown>;
  readonly result?: unknown;
  readonly isError?: boolean;
}

const createMessageId = (): string => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `assistant-chat-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
};

export const createTextMessage = (
  role: ThreadMessageLike['role'],
  text: string,
  status?: MessageStatus
): ThreadMessageLike => ({
  id: createMessageId(),
  role,
  content: [{ type: 'text', text }],
  status,
});

const isTextPart = (part: unknown): part is TextMessagePart => {
  if (typeof part !== 'object' || part === null) return false;
  return 'type' in part && part.type === 'text' && 'text' in part && typeof part.text === 'string';
};

export const isToolCallPart = (part: unknown): part is ToolCallContentPart => {
  if (typeof part !== 'object' || part === null) return false;
  return (
    'type' in part &&
    (part as { type: unknown }).type === 'tool-call' &&
    'toolName' in part &&
    typeof (part as { toolName: unknown }).toolName === 'string'
  );
};

export const getMessageText = (message: Pick<ThreadMessageLike, 'content'>): string => {
  if (typeof message.content === 'string') return message.content;
  return message.content
    .filter(isTextPart)
    .map((part) => part.text)
    .join('\n');
};

export const getToolCallParts = (
  message: Pick<ThreadMessageLike, 'content'>
): readonly ToolCallContentPart[] => {
  if (typeof message.content === 'string') return [];
  return (message.content as readonly unknown[]).filter((part): part is ToolCallContentPart =>
    isToolCallPart(part)
  );
};

export const appendMessageToThreadMessage = (message: AppendMessage): ThreadMessageLike => ({
  id: createMessageId(),
  role: message.role,
  content: message.content,
});

const stringifyToolResult = (result: unknown): string => {
  if (typeof result === 'string') return result;
  try {
    return JSON.stringify(result ?? null);
  } catch {
    return String(result);
  }
};

const toToolCall = (part: ToolCallContentPart, index: number): ChatCompletionMessageToolCall => ({
  id: part.toolCallId || `tool-call-${index}`,
  type: 'function',
  function: {
    name: part.toolName,
    arguments: part.argsText ?? (part.args ? JSON.stringify(part.args) : '{}'),
  },
});

const buildAssistantMessages = (message: ThreadMessageLike): ChatCompletionMessageParam[] => {
  const text = getMessageText(message);
  const toolCalls = getToolCallParts(message);

  if (toolCalls.length === 0) {
    return text ? [{ role: 'assistant', content: text }] : [];
  }

  const assistantMessage: ChatCompletionAssistantMessageParam = {
    role: 'assistant',
    content: text || null,
    tool_calls: toolCalls.map(toToolCall),
  };

  const toolMessages: ChatCompletionToolMessageParam[] = toolCalls
    .filter((part) => part.result !== undefined)
    .map((part, index) => ({
      role: 'tool',
      tool_call_id: part.toolCallId || `tool-call-${index}`,
      content: stringifyToolResult(part.result),
    }));

  return [assistantMessage, ...toolMessages];
};

export const getOpenAIMessages = (
  messages: readonly ThreadMessageLike[],
  systemPrompt?: string
): ChatCompletionMessageParam[] => {
  const result: ChatCompletionMessageParam[] = [];
  for (const message of messages) {
    if (message.role === 'assistant') {
      result.push(...buildAssistantMessages(message));
      continue;
    }
    if (message.role === 'user' || message.role === 'system') {
      const content = getMessageText(message);
      if (content) result.push({ role: message.role, content } as ChatCompletionMessageParam);
    }
  }

  if (!systemPrompt) return result;
  const withoutSystem = result.filter((message) => message.role !== 'system');
  return [{ role: 'system', content: systemPrompt }, ...withoutSystem];
};

const getMessageIndex = (
  messages: readonly ThreadMessageLike[],
  messageId: string | null | undefined
): number => {
  if (!messageId) return -1;

  const explicitIndex = messages.findIndex((message) => message.id === messageId);
  if (explicitIndex !== -1) return explicitIndex;

  const fallbackIndex = Number(messageId);
  return Number.isInteger(fallbackIndex) &&
    fallbackIndex >= 0 &&
    fallbackIndex < messages.length &&
    String(fallbackIndex) === messageId
    ? fallbackIndex
    : -1;
};

export const getEditedMessageIndex = (
  messages: readonly ThreadMessageLike[],
  message: AppendMessage
): number => {
  const sourceIndex = getMessageIndex(messages, message.sourceId);
  if (sourceIndex !== -1) return sourceIndex;

  if (message.parentId === null) return 0;

  const parentIndex = getMessageIndex(messages, message.parentId);
  return parentIndex === -1 ? -1 : parentIndex + 1;
};
