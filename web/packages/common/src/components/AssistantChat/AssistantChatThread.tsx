// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ActionBarPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  type ToolCallMessagePartComponent,
} from '@assistant-ui/react';
import { ComposerMode } from '@nemo/common/src/components/AssistantChat/types';
import { ChatEmptyState } from '@nemo/common/src/components/Chat/ChatEmptyState';
import {
  MessageContent,
  type MessageContentProps,
} from '@nemo/common/src/components/Chat/MessageContent';
import {
  Banner,
  Button,
  Flex,
  Skeleton,
  Stack,
  Text,
  TextArea,
  Tooltip,
} from '@nvidia/foundations-react-core';
import cn from 'classnames';
import { ArrowUp, Check, Copy, Pencil, RefreshCw, RotateCcw, Square, X } from 'lucide-react';
import { useCallback, useMemo, type ComponentProps, type ReactNode } from 'react';

export interface AssistantChatThreadAttributes {
  ThreadViewport?: ComponentProps<typeof ThreadPrimitive.Viewport>;
}

type AssistantChatMessageContentProps = Pick<MessageContentProps, 'markdownLinkComponent'>;

interface AssistantChatThreadProps {
  disabled?: boolean;
  placeholder: string;
  onReset: () => void;
  showRunningIndicator?: boolean;
  attributes?: AssistantChatThreadAttributes;
  composerMode?: ComposerMode;
  slotComposerStart?: ReactNode;
  emptyState?: {
    slotHeading?: string;
    slotSubheading?: string;
  };
  contentClassName?: string;
  composerContainerClassName?: string;
  hideAssistantMessageActions?: boolean;
  toolCallPartComponent?: ToolCallMessagePartComponent;
  viewportClassName?: string;
  composerOverride?: ReactNode;
  messageContentProps?: AssistantChatMessageContentProps;
}

const AssistantChatMessageContent = ({
  messageContentProps,
  toolCallPartComponent,
}: {
  messageContentProps?: AssistantChatMessageContentProps;
  toolCallPartComponent?: ToolCallMessagePartComponent;
}) => (
  <>
    <MessagePrimitive.Parts
      components={{
        Text: ({ text }) => <MessageContent content={text} {...messageContentProps} />,
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

const ACTION_BUTTON_CLASS =
  'flex cursor-pointer size-8 items-center justify-center rounded text-base bg-surface-raised hover:bg-surface-sunken disabled:cursor-not-allowed disabled:opacity-50';

const CHAT_VIEWPORT_SCROLLBAR_CLASS = [
  '[scrollbar-width:thin]',
  '[scrollbar-color:var(--border-color-interaction-base)_transparent]',
  '[&::-webkit-scrollbar]:w-2',
  '[&::-webkit-scrollbar-corner]:bg-transparent',
  '[&::-webkit-scrollbar-track]:bg-transparent',
  '[&::-webkit-scrollbar-thumb]:rounded-full',
  '[&::-webkit-scrollbar-thumb]:bg-[var(--border-color-interaction-base)]',
  '[&::-webkit-scrollbar-thumb:hover]:bg-[var(--border-color-interaction-strong)]',
].join(' ');

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

const AssistantMessage = ({
  hideAssistantMessageActions,
  messageContentProps,
  showRunningIndicator = true,
  toolCallPartComponent,
}: {
  hideAssistantMessageActions?: boolean;
  messageContentProps?: AssistantChatMessageContentProps;
  showRunningIndicator?: boolean;
  toolCallPartComponent?: ToolCallMessagePartComponent;
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
        <ActionBarPrimitive.Root
          hideWhenRunning
          className="flex gap-density-xs opacity-0 transition-opacity group-hover/message:opacity-100 group-focus-within/message:opacity-100 [@media(hover:none)]:opacity-100"
        >
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

const UserMessage = ({
  messageContentProps,
  toolCallPartComponent,
}: {
  messageContentProps?: AssistantChatMessageContentProps;
  toolCallPartComponent?: ToolCallMessagePartComponent;
}) => (
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
      <ActionBarPrimitive.Root
        hideWhenRunning
        className="flex gap-density-xs opacity-0 transition-opacity group-hover/message:opacity-100 group-focus-within/message:opacity-100 [@media(hover:none)]:opacity-100"
      >
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

const UserEditComposer = () => (
  <MessagePrimitive.Root
    data-testid="assistant-chat-edit-composer"
    className="w-full max-w-[80%] self-end rounded-xl rounded-br-none bg-surface-overlay px-4 py-2"
  >
    <ComposerPrimitive.Root className="w-full">
      <ComposerPrimitive.Input
        aria-label="Edit message"
        addAttachmentOnPaste={false}
        autoFocus
        submitMode="enter"
        rows={3}
        render={
          <TextArea
            resizeable="auto"
            size="large"
            className="w-full max-h-64"
            slotEnd={
              <Flex
                gap="density-sm"
                align="center"
                justify="end"
                className="mt-density-sm self-end"
              >
                <Tooltip slotContent="Cancel edit">
                  <ComposerPrimitive.Cancel
                    aria-label="Cancel edit"
                    className="cursor-pointer flex size-8 items-center justify-center rounded border border-base bg-surface-raised hover:bg-surface-sunken disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <X />
                  </ComposerPrimitive.Cancel>
                </Tooltip>
                <ComposerPrimitive.Send asChild>
                  <Button aria-label="Save edit" color="brand" size="small" className="h-full">
                    <Text kind="label/regular/sm">Send</Text>
                  </Button>
                </ComposerPrimitive.Send>
              </Flex>
            }
          />
        }
      />
    </ComposerPrimitive.Root>
  </MessagePrimitive.Root>
);

type AssistantComposerProps = Pick<
  AssistantChatThreadProps,
  'disabled' | 'placeholder' | 'onReset' | 'slotComposerStart'
> & {
  className?: string;
};

const AssistantComposer = ({
  disabled,
  placeholder,
  onReset,
  slotComposerStart,
  className,
}: AssistantComposerProps) => (
  <div className="flex w-full flex-col gap-2">
    {slotComposerStart && <div className="shrink-0">{slotComposerStart}</div>}
    <ComposerPrimitive.Root
      data-testid="assistant-chat-composer"
      className={cn(
        'flex w-full items-end gap-density-xs rounded-lg border border-base bg-surface-base p-1',
        className
      )}
    >
      <ComposerPrimitive.Input
        aria-label="Task prompt"
        addAttachmentOnPaste={false}
        disabled={disabled}
        placeholder={placeholder}
        submitMode="enter"
        className="max-h-32 min-h-[24px] flex-1 resize-none border-0 bg-transparent px-density-md py-density-md text-sm leading-6 outline-none disabled:cursor-not-allowed disabled:text-fg-disabled"
      />
      <Tooltip slotContent="Clear chat thread">
        <Button
          aria-label="Reset"
          kind="tertiary"
          size="small"
          onClick={onReset}
          type="button"
          disabled={disabled}
        >
          <RotateCcw />
        </Button>
      </Tooltip>
      <ThreadPrimitive.If running>
        <ComposerPrimitive.Cancel asChild>
          <Button aria-label="Stop" color="danger" size="small" className="size-8 rounded-full p-0">
            <Square size={14} />
          </Button>
        </ComposerPrimitive.Cancel>
      </ThreadPrimitive.If>
      <ThreadPrimitive.If running={false}>
        <ComposerPrimitive.Send asChild>
          <Button
            aria-label="Submit"
            color="brand"
            size="small"
            className="size-8 rounded-full p-0"
          >
            <ArrowUp size={16} />
          </Button>
        </ComposerPrimitive.Send>
      </ThreadPrimitive.If>
    </ComposerPrimitive.Root>
  </div>
);

export const AssistantChatThread = ({
  disabled,
  placeholder,
  onReset,
  showRunningIndicator = true,
  attributes,
  composerMode = ComposerMode.PER_PANEL,
  slotComposerStart,
  emptyState,
  contentClassName,
  composerContainerClassName,
  hideAssistantMessageActions,
  toolCallPartComponent,
  viewportClassName,
  composerOverride,
  messageContentProps,
}: AssistantChatThreadProps) => {
  const { className: threadViewportClassName, ...threadViewportAttributes } =
    attributes?.ThreadViewport ?? {};
  const AssistantMessageWithToolCallPart = useCallback(
    () => (
      <AssistantMessage
        hideAssistantMessageActions={hideAssistantMessageActions}
        messageContentProps={messageContentProps}
        showRunningIndicator={showRunningIndicator}
        toolCallPartComponent={toolCallPartComponent}
      />
    ),
    [hideAssistantMessageActions, messageContentProps, showRunningIndicator, toolCallPartComponent]
  );
  const UserMessageWithToolCallPart = useCallback(
    () => (
      <UserMessage
        messageContentProps={messageContentProps}
        toolCallPartComponent={toolCallPartComponent}
      />
    ),
    [messageContentProps, toolCallPartComponent]
  );
  const messageComponents = useMemo(
    () => ({
      AssistantMessage: AssistantMessageWithToolCallPart,
      UserMessage: UserMessageWithToolCallPart,
      UserEditComposer,
      SystemMessage: AssistantMessageWithToolCallPart,
    }),
    [AssistantMessageWithToolCallPart, UserMessageWithToolCallPart]
  );

  return (
    <ThreadPrimitive.Root className="flex h-full w-full flex-col" role="log">
      <div className="relative min-h-0 flex-1">
        <ThreadPrimitive.Viewport
          {...threadViewportAttributes}
          data-testid="assistant-chat-viewport"
          className={cn(
            'flex h-full min-h-0 flex-col overflow-y-auto',
            CHAT_VIEWPORT_SCROLLBAR_CLASS,
            viewportClassName,
            threadViewportClassName
          )}
        >
          <Stack gap="density-sm" className={cn('min-h-full w-full', contentClassName)}>
            <ThreadPrimitive.Empty>
              <ChatEmptyState
                className="h-full min-h-[250px] w-full"
                slotHeading={emptyState?.slotHeading}
                slotSubheading={emptyState?.slotSubheading}
              />
            </ThreadPrimitive.Empty>
            <ThreadPrimitive.Messages components={messageComponents} />
          </Stack>
        </ThreadPrimitive.Viewport>
        <ThreadPrimitive.ScrollToBottom className="absolute bottom-density-sm left-1/2 z-10 -translate-x-1/2 rounded border border-base bg-surface-raised px-density-sm py-density-xs text-sm shadow disabled:hidden">
          Scroll to bottom
        </ThreadPrimitive.ScrollToBottom>
      </div>
      {composerMode !== ComposerMode.BROADCAST_ALL && (
        <Flex
          className={cn('w-full pt-density-xl', composerContainerClassName)}
          data-testid="assistant-chat-composer-container"
        >
          {composerOverride ?? (
            <AssistantComposer
              disabled={disabled}
              placeholder={placeholder}
              onReset={onReset}
              slotComposerStart={slotComposerStart}
            />
          )}
        </Flex>
      )}
    </ThreadPrimitive.Root>
  );
};
