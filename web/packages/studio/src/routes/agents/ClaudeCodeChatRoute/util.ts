// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ThreadAssistantMessagePart, ThreadMessageLike } from '@assistant-ui/react';
import { COMPLETE_STATUS } from '@nemo/common/src/components/AssistantChat/constants';
import {
  createClaudeCodeToolCallPart,
  isClaudeCodeToolCallOmitted,
} from '@studio/routes/agents/ClaudeCodeChatRoute/toolParts';
import type {
  ClaudeCodeAssistantHistoryPart,
  ClaudeCodeSessionHistory,
} from '@studio/routes/agents/ClaudeCodeChatRoute/types';
import { getClaudeCodeChatRoute } from '@studio/routes/utils';

export const CLAUDE_CODE_SESSION_SEARCH_PARAM = 'session';

export const getClaudeCodeChatRouteForSession = (workspace: string, sessionId: string): string => {
  const searchParams = new URLSearchParams({
    [CLAUDE_CODE_SESSION_SEARCH_PARAM]: sessionId,
  });
  return `${getClaudeCodeChatRoute(workspace)}?${searchParams.toString()}`;
};

export const getSelectedClaudeCodeSessionId = (search: string): string | undefined => {
  const sessionId = new URLSearchParams(search).get(CLAUDE_CODE_SESSION_SEARCH_PARAM)?.trim();
  return sessionId || undefined;
};

const getAssistantMessagePart = (
  part: ClaudeCodeAssistantHistoryPart,
  index: number
): ThreadAssistantMessagePart | undefined => {
  if (part.type === 'thinking') return { type: 'reasoning', text: part.thinking };
  if (part.type === 'text') return { type: 'text', text: part.text };
  if (part.type === 'tool_use') {
    const toolName = part.name || 'tool';
    if (isClaudeCodeToolCallOmitted(toolName)) return undefined;

    return createClaudeCodeToolCallPart({
      input: part.input,
      toolCallId: `claude-history-tool-${toolName}-${index}`,
      toolName,
    });
  }
  return undefined;
};

export const getClaudeCodeHistoryMessages = (
  history: ClaudeCodeSessionHistory | undefined
): readonly ThreadMessageLike[] => {
  if (!history) return [];

  return history.items
    .map((item, index): ThreadMessageLike | undefined => {
      if (item.kind === 'user') {
        return {
          id: `${history.session_id}-${index}`,
          role: 'user',
          content: [{ type: 'text', text: item.text }],
        };
      }

      const content = item.parts
        .map(getAssistantMessagePart)
        .filter((part): part is ThreadAssistantMessagePart => part !== undefined);
      if (!content.length) return undefined;

      return {
        id: `${history.session_id}-${index}`,
        role: 'assistant',
        content,
        status: COMPLETE_STATUS,
      };
    })
    .filter((message): message is ThreadMessageLike => message !== undefined);
};
