// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ActionBarPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
} from '@assistant-ui/react';
import {
  ASSISTANT_MESSAGE_SURFACE_CLASS,
  AssistantChatMessageContent,
} from '@nemo/common/src/components/AssistantChat/AssistantChatMessageContent';
import {
  ACTION_BUTTON_CLASS,
  CopyAction,
  MESSAGE_ACTIONS_CLASS,
} from '@nemo/common/src/components/AssistantChat/messageActions';
import type { MessageRenderProps } from '@nemo/common/src/components/AssistantChat/types';
import { Skeleton, Tooltip } from '@nvidia/foundations-react-core';
import { RefreshCw } from 'lucide-react';

export const AssistantMessage = ({
  hideAssistantMessageActions,
  hideEmptyRunningMessageSurface = false,
  messageContentProps,
  separateMessageParts = false,
  showRunningIndicator = true,
  toolCallPartComponent,
}: MessageRenderProps & {
  hideAssistantMessageActions?: boolean;
  hideEmptyRunningMessageSurface?: boolean;
  separateMessageParts?: boolean;
  showRunningIndicator?: boolean;
}) => {
  const isEmptyRunningMessage = useAuiState((state) => {
    const { parts } = state.message;
    const hasVisibleContent = parts.some(
      (part) => part.type !== 'text' || part.text.trim().length > 0
    );

    return state.message.status?.type === 'running' && !hasVisibleContent;
  });
  const isToolOnlyMessage = useAuiState((state) => {
    const { parts } = state.message;
    return parts.length > 0 && parts.every((part) => part.type === 'tool-call');
  });

  return (
    <MessagePrimitive.Root
      data-testid="assistant-chat-message"
      data-testspeaker="assistant"
      className="group/message flex w-full flex-col items-start gap-density-xs whitespace-normal"
    >
      {separateMessageParts ? (
        <AssistantChatMessageContent
          messageContentProps={messageContentProps}
          separateTextParts
          toolCallPartComponent={toolCallPartComponent}
        />
      ) : isToolOnlyMessage ? (
        <AssistantChatMessageContent
          messageContentProps={messageContentProps}
          toolCallPartComponent={toolCallPartComponent}
        />
      ) : hideEmptyRunningMessageSurface && isEmptyRunningMessage ? null : (
        <div
          className={ASSISTANT_MESSAGE_SURFACE_CLASS}
          data-testid="assistant-chat-message-surface"
        >
          <AssistantChatMessageContent
            messageContentProps={messageContentProps}
            toolCallPartComponent={toolCallPartComponent}
          />
        </div>
      )}
      {showRunningIndicator ? (
        <MessagePrimitive.If last>
          <ThreadPrimitive.If running>
            <div
              className="flex h-6 w-full items-center"
              data-testid="assistant-chat-running-indicator"
            >
              <Skeleton className="h-density-4 w-full" data-testid="assistant-chat-skeleton" />
            </div>
          </ThreadPrimitive.If>
        </MessagePrimitive.If>
      ) : null}
      {!hideAssistantMessageActions ? (
        <div
          className="flex h-7 items-center pl-density-xs"
          data-testid="assistant-chat-message-actions"
        >
          <ActionBarPrimitive.Root hideWhenRunning className={MESSAGE_ACTIONS_CLASS}>
            <Tooltip slotContent="Regenerate response">
              <ActionBarPrimitive.Reload
                aria-label="Regenerate response"
                className={ACTION_BUTTON_CLASS}
              >
                <RefreshCw size={16} />
              </ActionBarPrimitive.Reload>
            </Tooltip>
            <CopyAction />
          </ActionBarPrimitive.Root>
        </div>
      ) : null}
    </MessagePrimitive.Root>
  );
};
