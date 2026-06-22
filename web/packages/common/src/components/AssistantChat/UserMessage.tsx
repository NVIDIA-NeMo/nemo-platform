// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ActionBarPrimitive, MessagePrimitive } from '@assistant-ui/react';
import { AssistantChatMessageContent } from '@nemo/common/src/components/AssistantChat/AssistantChatMessageContent';
import {
  ACTION_BUTTON_CLASS,
  CopyAction,
  MESSAGE_ACTIONS_CLASS,
} from '@nemo/common/src/components/AssistantChat/messageActions';
import type { MessageRenderProps } from '@nemo/common/src/components/AssistantChat/types';
import { Tooltip } from '@nvidia/foundations-react-core';
import { Pencil } from 'lucide-react';

export const UserMessage = ({ messageContentProps, toolCallPartComponent }: MessageRenderProps) => (
  <MessagePrimitive.Root
    data-testid="assistant-chat-message"
    data-testspeaker="user"
    className="group/message flex w-full flex-col items-end gap-density-xs whitespace-normal"
  >
    <div className="max-w-[80%] rounded-xl rounded-br-none bg-surface-overlay px-3 py-2">
      <AssistantChatMessageContent
        messageContentProps={messageContentProps}
        toolCallPartComponent={toolCallPartComponent}
      />
    </div>
    <div className="flex h-8 shrink-0 items-center">
      <ActionBarPrimitive.Root hideWhenRunning className={MESSAGE_ACTIONS_CLASS}>
        <Tooltip slotContent="Edit message">
          <ActionBarPrimitive.Edit aria-label="Edit message" className={ACTION_BUTTON_CLASS}>
            <Pencil size={16} />
          </ActionBarPrimitive.Edit>
        </Tooltip>
        <CopyAction />
      </ActionBarPrimitive.Root>
    </div>
  </MessagePrimitive.Root>
);
