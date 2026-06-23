// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ActionBarPrimitive, MessagePrimitive, ThreadPrimitive } from '@assistant-ui/react';
import { AssistantChatMessageContent } from '@nemo/common/src/components/AssistantChat/AssistantChatMessageContent';
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
  messageContentProps,
  showRunningIndicator = true,
  toolCallPartComponent,
}: MessageRenderProps & {
  hideAssistantMessageActions?: boolean;
  showRunningIndicator?: boolean;
}) => (
  <MessagePrimitive.Root
    data-testid="assistant-chat-message"
    data-testspeaker="assistant"
    className="group/message self-stretch whitespace-normal"
  >
    <AssistantChatMessageContent
      messageContentProps={messageContentProps}
      toolCallPartComponent={toolCallPartComponent}
    />
    {showRunningIndicator ? (
      <MessagePrimitive.If last>
        <ThreadPrimitive.If running>
          <div
            className="mt-density-xs flex h-6 items-center"
            data-testid="assistant-chat-running-indicator"
          >
            <Skeleton className="h-density-4 w-full" data-testid="assistant-chat-skeleton" />
          </div>
        </ThreadPrimitive.If>
      </MessagePrimitive.If>
    ) : null}
    {!hideAssistantMessageActions ? (
      <div
        className="mt-density-xs flex h-8 items-center"
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
