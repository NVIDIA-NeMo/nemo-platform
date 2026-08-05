// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ThreadAssistantMessagePart, ThreadMessageLike } from '@assistant-ui/react';
import { COMPLETE_STATUS } from '@nemo/common/src/components/AssistantChat/constants';
import {
  createCopilotToolCallPart,
  getCopilotCompletedMessageParts,
  groupConsecutiveCopilotSubtleToolCalls,
  mergeConsecutiveCopilotSubtleToolMessages,
  STUDIO_MESSAGE_SUMMARY_START,
} from '@studio/routes/agents/CopilotChatRoute/toolParts';
import type {
  CopilotAssistantHistoryPart,
  CopilotSessionHistory,
} from '@studio/routes/agents/CopilotChatRoute/types';
import { getCopilotChatRoute } from '@studio/routes/utils';

export const COPILOT_SESSION_SEARCH_PARAM = 'session';

export const getCopilotChatRouteForSession = (workspace: string, sessionId: string): string => {
  const searchParams = new URLSearchParams({
    [COPILOT_SESSION_SEARCH_PARAM]: sessionId,
  });
  return `${getCopilotChatRoute(workspace)}?${searchParams.toString()}`;
};

export const getSelectedCopilotSessionId = (search: string): string | undefined => {
  const sessionId = new URLSearchParams(search).get(COPILOT_SESSION_SEARCH_PARAM)?.trim();
  return sessionId || undefined;
};

const getAssistantMessagePart = (
  part: CopilotAssistantHistoryPart,
  index: number,
  assistantMessageId: string
): ThreadAssistantMessagePart | undefined => {
  if (part.type === 'text') return { type: 'text', text: part.text };
  if (part.type === 'tool_use') {
    const toolName = part.name || 'tool';
    const trimmedId = typeof part.id === 'string' ? part.id.trim() : '';
    const toolCallId =
      trimmedId || `copilot-history-tool-${assistantMessageId}-${toolName}-${index}`;

    return createCopilotToolCallPart({
      input: part.input,
      toolCallId,
      toolName,
    });
  }
  return undefined;
};

const getAssistantContent = (
  message: ThreadMessageLike
): readonly ThreadAssistantMessagePart[] | undefined =>
  message.role === 'assistant' && Array.isArray(message.content) ? message.content : undefined;

const hasStudioSummaryMarker = (message: ThreadMessageLike): boolean =>
  getAssistantContent(message)?.some(
    (part) => part.type === 'text' && part.text.includes(STUDIO_MESSAGE_SUMMARY_START)
  ) ?? false;

const combineAssistantRunMessages = (
  messages: readonly ThreadMessageLike[]
): readonly ThreadMessageLike[] => {
  const combinedMessages: ThreadMessageLike[] = [];
  let pendingAssistantMessages: ThreadMessageLike[] = [];

  const flushPendingAssistantMessages = () => {
    if (!pendingAssistantMessages.length) return;

    if (!pendingAssistantMessages.some(hasStudioSummaryMarker)) {
      combinedMessages.push(...pendingAssistantMessages);
      pendingAssistantMessages = [];
      return;
    }

    const firstMessage = pendingAssistantMessages[0]!;
    const lastMessage = pendingAssistantMessages[pendingAssistantMessages.length - 1]!;
    combinedMessages.push({
      ...lastMessage,
      id: firstMessage.id ?? lastMessage.id,
      content: pendingAssistantMessages.flatMap((message) => getAssistantContent(message) ?? []),
      status: COMPLETE_STATUS,
    });
    pendingAssistantMessages = [];
  };

  for (const message of messages) {
    if (message.role === 'assistant') {
      pendingAssistantMessages.push(message);
      continue;
    }

    flushPendingAssistantMessages();
    combinedMessages.push(message);
  }

  flushPendingAssistantMessages();
  return combinedMessages;
};

export const getCopilotHistoryMessages = (
  history: CopilotSessionHistory | undefined
): readonly ThreadMessageLike[] => {
  if (!history) return [];

  const messages = history.items
    .map((item, index): ThreadMessageLike | undefined => {
      if (item.kind === 'user') {
        return {
          id: `${history.session_id}-${index}`,
          role: 'user',
          content: [{ type: 'text', text: item.text }],
        };
      }

      const messageId = `${history.session_id}-${index}`;
      const content = item.parts
        .map((part, partIndex) => getAssistantMessagePart(part, partIndex, messageId))
        .filter((part): part is ThreadAssistantMessagePart => part !== undefined);
      const groupedContent = groupConsecutiveCopilotSubtleToolCalls(content);
      if (!groupedContent.length) return undefined;

      return {
        id: messageId,
        role: 'assistant',
        content: groupedContent,
        status: COMPLETE_STATUS,
      };
    })
    .filter((message): message is ThreadMessageLike => message !== undefined);

  return mergeConsecutiveCopilotSubtleToolMessages(combineAssistantRunMessages(messages)).map(
    (message) =>
      message.role === 'assistant' && Array.isArray(message.content)
        ? { ...message, content: getCopilotCompletedMessageParts(message.content) }
        : message
  );
};
