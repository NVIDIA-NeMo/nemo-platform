// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ActionBarPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
  type TextMessagePartComponent,
  ThreadPrimitive,
} from '@assistant-ui/react';
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
import { Check, Copy, Pencil, RefreshCw, RotateCcw, Send, Square, X } from 'lucide-react';
import type { ComponentProps, ReactNode } from 'react';

import { ChatEmptyState } from '../Chat/ChatEmptyState';
import { MessageContent } from '../Chat/MessageContent';

export interface AssistantChatThreadAttributes {
  ThreadViewport?: ComponentProps<typeof ThreadPrimitive.Viewport>;
}

interface AssistantChatThreadProps {
  disabled?: boolean;
  placeholder: string;
  onReset: () => void;
  showRunningIndicator?: boolean;
  attributes?: AssistantChatThreadAttributes;
  emptyState?: {
    slotHeading?: string;
    slotSubheading?: string;
  };
  contentClassName?: string;
  composerContainerClassName?: string;
  viewportClassName?: string;
  composerOverride?: ReactNode;
}

const AssistantChatTextPart: TextMessagePartComponent = ({ text }) => (
  <MessageContent content={text} />
);

const AssistantChatMessageContent = () => (
  <>
    <MessagePrimitive.Parts components={{ Text: AssistantChatTextPart }} />
    <MessagePrimitive.Error>
      <Banner kind="inline" status="error" className="mt-density-sm">
        There was an error generating a response.
      </Banner>
    </MessagePrimitive.Error>
  </>
);

const ACTION_BUTTON_CLASS =
  'flex cursor-pointer size-8 items-center justify-center rounded text-base bg-surface-raised hover:bg-surface-sunken disabled:cursor-not-allowed disabled:opacity-50';

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

const AssistantMessage = ({ showRunningIndicator = true }: { showRunningIndicator?: boolean }) => (
  <MessagePrimitive.Root
    data-testid="assistant-chat-message"
    data-testspeaker="assistant"
    className="group/message self-stretch whitespace-pre-wrap"
  >
    <AssistantChatMessageContent />
    {showRunningIndicator ? (
      <div className="mt-density-sm flex h-8 items-center">
        <MessagePrimitive.If last>
          <ThreadPrimitive.If running>
            <Skeleton className="h-density-4 w-full" data-testid="assistant-chat-skeleton" />
          </ThreadPrimitive.If>
        </MessagePrimitive.If>
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

const UserMessage = () => (
  <MessagePrimitive.Root
    data-testid="assistant-chat-message"
    data-testspeaker="user"
    className="group/message flex w-full flex-col items-end gap-density-xs whitespace-pre-wrap"
  >
    <div className="max-w-[80%] rounded-xl rounded-br-none bg-surface-overlay px-3 py-2">
      <AssistantChatMessageContent />
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
  'disabled' | 'placeholder' | 'onReset'
> & {
  className?: string;
};

const AssistantComposer = ({
  disabled,
  placeholder,
  onReset,
  className,
}: AssistantComposerProps) => (
  <ComposerPrimitive.Root
    className={cn(
      'flex w-full items-end gap-1 rounded border border-base bg-surface-base p-1',
      className
    )}
  >
    <ComposerPrimitive.Input
      aria-label="Task prompt"
      addAttachmentOnPaste={false}
      disabled={disabled}
      placeholder={placeholder}
      submitMode="enter"
      className="max-h-64 min-h-16 flex-1 resize-none border-0 bg-transparent p-density-sm text-sm outline-none disabled:cursor-not-allowed disabled:text-fg-disabled"
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
        <Button aria-label="Stop" color="danger" size="small">
          <Square />
        </Button>
      </ComposerPrimitive.Cancel>
    </ThreadPrimitive.If>
    <ThreadPrimitive.If running={false}>
      <ComposerPrimitive.Send asChild>
        <Button aria-label="Submit" color="brand" size="small">
          <Send />
        </Button>
      </ComposerPrimitive.Send>
    </ThreadPrimitive.If>
  </ComposerPrimitive.Root>
);

export const AssistantChatThread = ({
  disabled,
  placeholder,
  onReset,
  showRunningIndicator = true,
  attributes,
  emptyState,
  contentClassName,
  composerContainerClassName,
  viewportClassName,
  composerOverride,
}: AssistantChatThreadProps) => {
  const { className: threadViewportClassName, ...threadViewportAttributes } =
    attributes?.ThreadViewport ?? {};
  const AssistantMessageComponent = () => (
    <AssistantMessage showRunningIndicator={showRunningIndicator} />
  );

  return (
    <ThreadPrimitive.Root className="flex h-full w-full flex-col" role="log">
      <ThreadPrimitive.Viewport
        {...threadViewportAttributes}
        className={cn(
          'relative flex min-h-0 flex-1 flex-col overflow-y-auto',
          viewportClassName,
          threadViewportClassName
        )}
      >
        <Stack gap="density-md" className={cn('min-h-full w-full', contentClassName)}>
          <ThreadPrimitive.Empty>
            <ChatEmptyState
              className="h-full min-h-[250px] w-full"
              slotHeading={emptyState?.slotHeading}
              slotSubheading={emptyState?.slotSubheading}
            />
          </ThreadPrimitive.Empty>
          <ThreadPrimitive.Messages
            components={{
              AssistantMessage: AssistantMessageComponent,
              UserMessage,
              UserEditComposer,
              SystemMessage: AssistantMessageComponent,
            }}
          />
        </Stack>
        <ThreadPrimitive.ScrollToBottom className="sticky bottom-density-sm self-center rounded border border-base bg-surface-raised px-density-sm py-density-xs text-sm shadow disabled:hidden">
          Scroll to bottom
        </ThreadPrimitive.ScrollToBottom>
      </ThreadPrimitive.Viewport>
      <Flex className={cn('w-full', composerContainerClassName)}>
        {composerOverride ?? (
          <AssistantComposer disabled={disabled} placeholder={placeholder} onReset={onReset} />
        )}
      </Flex>
    </ThreadPrimitive.Root>
  );
};
