// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ChatCompletion,
  ChatCompletionChunk,
  ChatCompletionMessageParam,
} from 'openai/resources/index.mjs';

import { ExcludedChatCompletionMessageParam } from '../types/chat';

/**
 * Given a message, return the content as a string. If the content is an array, join the array into a string.
 */
export const getContentFromMessage = (message?: ChatCompletionMessageParam): string => {
  if (!message?.content) {
    return '';
  } else if (Array.isArray(message.content)) {
    const content = message.content
      .map((c) => {
        if (c.type === 'text') {
          return c.text;
        } else if (c.type === 'image_url') {
          return c.image_url.url;
        } else if (c.type === 'refusal') {
          return c.refusal;
        }
        return '';
      })
      .join(' ');
    return content;
  }
  return message.content;
};

/**
 * Given a Chunk choice or Completion choice, return the delta or message. Useful for asserting the type of a response and indexing
 * keys relevant to the type.
 */
export const getDeltaOrMessage = (response: ChatCompletionChunk.Choice | ChatCompletion.Choice) => {
  if ('delta' in response) {
    return response.delta;
  }
  return response.message;
};

export const maybeInsertSystemMessage = (
  messages: ExcludedChatCompletionMessageParam[],
  systemPrompt?: string
): ExcludedChatCompletionMessageParam[] => {
  const parsedMessages = messages.map((message) => {
    if (message.role === 'assistant' && message.content === '' && message.tool_calls) {
      return {
        ...message,
        content: JSON.stringify(message.tool_calls),
      };
    }
    return message;
  });

  if (!systemPrompt) {
    return parsedMessages;
  }

  return [
    {
      role: 'system',
      content: systemPrompt,
    },
    ...parsedMessages,
  ];
};
