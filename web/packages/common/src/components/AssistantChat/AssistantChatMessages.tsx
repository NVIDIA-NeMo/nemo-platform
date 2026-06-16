// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ActionBarPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  type ToolCallMessagePartComponent,
} from '@assistant-ui/react';
import { ComposerAttachmentsRow } from '@nemo/common/src/components/AssistantChat/ComposerAttachments';
import type { AssistantChatMessageContentProps } from '@nemo/common/src/components/AssistantChat/types';
import { MessageContent } from '@nemo/common/src/components/Chat/MessageContent';
import {
  Banner,
  Button,
  Flex,
  Skeleton,
  Text,
  TextArea,
  Tooltip,
} from '@nvidia/foundations-react-core';
import { Check, Copy, ImagePlus, Pencil, RefreshCw, X } from 'lucide-react';

interface MessageRenderProps {
  messageContentProps?: AssistantChatMessageContentProps;
  toolCallPartComponent?: ToolCallMessagePartComponent;
}

const ACTION_BUTTON_CLASS =
  'flex cursor-pointer size-8 items-center justify-center rounded text-base bg-surface-raised hover:bg-surface-sunken disabled:cursor-not-allowed disabled:opacity-50';

const MESSAGE_ACTIONS_CLASS =
  'flex gap-density-xs opacity-0 transition-opacity group-hover/message:opacity-100 group-focus-within/message:opacity-100 [@media(hover:none)]:opacity-100';

const AssistantChatMessageContent = ({
  messageContentProps,
  toolCallPartComponent,
}: MessageRenderProps) => (
  <>
    <MessagePrimitive.Parts
      components={{
        Text: ({ text }) => <MessageContent content={text} {...messageContentProps} />,
        Image: ({ image, filename }) => (
          <img
            src={image}
            alt={filename ?? 'Attached image'}
            className="mt-density-xs max-h-64 w-auto rounded-lg border border-base object-contain"
          />
        ),
        tools: { Fallback: toolCallPartComponent },
      }}
    />
    <MessagePrimitive.Error>
      <Banner kind="inline" status="error" className="mt-density-sm">
        There was an error generating a response.
      </Banner>
    </MessagePrimitive.Error>
  </>
);

const CopyAction = () => (
  <Tooltip slotContent="Copy message">
    <ActionBarPrimitive.Copy aria-label="Copy message" className={ACTION_BUTTON_CLASS}>
      <MessagePrimitive.If copied>
        <Check size={16} />
      </MessagePrimitive.If>
      <MessagePrimitive.If copied={false}>
        <Copy size={16} />
      </MessagePrimitive.If>
    </ActionBarPrimitive.Copy>
  </Tooltip>
);

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

export const UserEditComposer = ({
  enableImageAttachments = true,
}: {
  enableImageAttachments?: boolean;
}) => (
  <MessagePrimitive.Root
    data-testid="assistant-chat-edit-composer"
    className="w-full max-w-[80%] self-end rounded-xl rounded-br-none bg-surface-overlay px-3 py-2"
  >
    {/*
      Lay the textarea and the action row out as siblings in a column. Nesting
      the buttons in the TextArea's `slotEnd` let a growing textarea push them
      out of the bubble — a separate row pins them in place while the input
      scrolls within `max-h-64`.
    */}
    <ComposerPrimitive.Root className="flex w-full flex-col gap-density-sm">
      {enableImageAttachments && <ComposerAttachmentsRow />}
      <ComposerPrimitive.Input
        aria-label="Edit message"
        addAttachmentOnPaste={enableImageAttachments}
        autoFocus
        submitMode="enter"
        rows={3}
        render={<TextArea resizeable="auto" size="large" className="w-full max-h-64" />}
      />
      <Flex gap="density-sm" align="center" justify="end">
        {enableImageAttachments && (
          <Tooltip slotContent="Add image">
            <ComposerPrimitive.AddAttachment asChild>
              <Button
                aria-label="Add image"
                kind="tertiary"
                size="small"
                type="button"
                className="mr-auto"
              >
                <ImagePlus size={16} />
              </Button>
            </ComposerPrimitive.AddAttachment>
          </Tooltip>
        )}
        <Tooltip slotContent="Cancel edit">
          <ComposerPrimitive.Cancel
            aria-label="Cancel edit"
            className="cursor-pointer flex size-8 items-center justify-center rounded border border-base bg-surface-raised hover:bg-surface-sunken disabled:cursor-not-allowed disabled:opacity-50"
          >
            <X />
          </ComposerPrimitive.Cancel>
        </Tooltip>
        <ComposerPrimitive.Send asChild>
          <Button aria-label="Save edit" color="brand" size="small">
            <Text kind="label/regular/sm">Send</Text>
          </Button>
        </ComposerPrimitive.Send>
      </Flex>
    </ComposerPrimitive.Root>
  </MessagePrimitive.Root>
);
