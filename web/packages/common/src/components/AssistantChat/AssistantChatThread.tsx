// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ComposerPrimitive,
  MessagePrimitive,
  type TextMessagePartComponent,
  ThreadPrimitive,
  useMessage,
} from '@assistant-ui/react';
import {
  Banner,
  Button,
  Flex,
  Skeleton,
  Stack,
  Tooltip,
} from '@nvidia/foundations-react-core';
import cn from 'classnames';
import { Gauge, Hash, RotateCcw, Send, Square, Timer } from 'lucide-react';
import type * as React from 'react';

import { ChatEmptyState } from '../Chat/ChatEmptyState';
import { MessageContent } from '../Chat/MessageContent';
import type { AssistantMessageMetrics } from './types';

interface AssistantChatThreadProps {
  disabled?: boolean;
  placeholder: string;
  onReset: () => void;
  /** When true, suppresses the bottom composer — message thread still renders. */
  hideComposer?: boolean;
  /** Content rendered in a sub-row directly above the composer, INSIDE the
   *  same outer card. Used for seed-prompt chips so they read as part of the
   *  composer affordance rather than a separate block. */
  slotAboveComposer?: React.ReactNode;
  emptyState?: {
    slotHeading?: string;
    slotSubheading?: string;
  };
  composerVariant?: 'default' | 'playground';
  contentClassName?: string;
  composerContainerClassName?: string;
  viewportClassName?: string;
  assistantMessageMetricsById?: Record<string, AssistantMessageMetrics>;
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

const MessageMetrics = ({ metrics }: { metrics: AssistantMessageMetrics }) => (
  <div className="inline-flex items-center gap-4 text-xs font-mono text-[var(--color-brand)]">
    <span className="inline-flex items-center gap-1" title="Time to first token">
      <Timer size={12} />
      {(metrics.ttftMs / 1000).toFixed(1)}s
    </span>
    <span className="inline-flex items-center gap-1" title="Tokens per second">
      <Gauge size={12} />
      {metrics.tokensPerSec.toFixed(1)} t/s
    </span>
    <span className="inline-flex items-center gap-1" title="Completion tokens">
      <Hash size={12} />
      {metrics.completionTokens} tokens
    </span>
  </div>
);

const createAssistantMessage = (
  assistantMessageMetricsById?: Record<string, AssistantMessageMetrics>
) => {
  const AssistantMessage = () => {
    // Each turn renders its own metrics, keyed by this message's id, so the
    // whole conversation shows per-turn stats — not only the latest reply.
    const messageId = useMessage((message) => message.id);
    const metrics = messageId ? assistantMessageMetricsById?.[messageId] : undefined;
    return (
      <MessagePrimitive.Root
        data-testid="assistant-chat-message"
        data-testspeaker="assistant"
        className="group/message self-stretch whitespace-pre-wrap"
      >
        <AssistantChatMessageContent />
        <div className="mt-density-sm flex min-h-8 w-full items-center">
          <MessagePrimitive.If last>
            <ThreadPrimitive.If running>
              <Skeleton className="h-density-4 w-full" data-testid="assistant-chat-skeleton" />
            </ThreadPrimitive.If>
          </MessagePrimitive.If>
          {metrics ? (
            <div className="ml-auto">
              <MessageMetrics metrics={metrics} />
            </div>
          ) : null}
        </div>
      </MessagePrimitive.Root>
    );
  };

  return AssistantMessage;
};

const UserMessage = () => (
  <MessagePrimitive.Root
    data-testid="assistant-chat-message"
    data-testspeaker="user"
    className="group/message mt-density-xl flex w-full flex-col items-end gap-density-xs whitespace-pre-wrap"
  >
    <div className="max-w-[80%] rounded-xl rounded-br-none bg-surface-overlay px-3 py-2">
      <AssistantChatMessageContent />
    </div>
  </MessagePrimitive.Root>
);

type AssistantComposerProps = Pick<
  AssistantChatThreadProps,
  'disabled' | 'placeholder' | 'onReset' | 'slotAboveComposer' | 'composerVariant'
> & {
  className?: string;
};

const AssistantComposer = ({
  disabled,
  placeholder,
  onReset,
  slotAboveComposer,
  composerVariant = 'default',
  className,
}: AssistantComposerProps) => {
  if (composerVariant === 'playground') {
    return (
      <div className="flex flex-col gap-3">
        {slotAboveComposer ? <div className="shrink-0">{slotAboveComposer}</div> : null}
        <ComposerPrimitive.Root
          className={cn('relative w-full rounded-lg border border-base bg-surface-base', className)}
        >
          <ComposerPrimitive.Input
            aria-label="Task prompt"
            addAttachmentOnPaste={false}
            disabled={disabled}
            placeholder={placeholder}
            submitMode="enter"
            rows={3}
            className="max-h-64 min-h-[88px] w-full resize-none border-0 bg-transparent p-3 pb-14 text-sm outline-none disabled:cursor-not-allowed disabled:text-fg-disabled"
          />
          <Flex gap="density-sm" align="center" justify="end" className="absolute bottom-2 right-2">
            <Tooltip slotContent="Clear chat thread">
              <Button
                aria-label="Reset"
                kind="tertiary"
                size="small"
                onClick={onReset}
                type="button"
                disabled={disabled}
              >
                <RotateCcw size={16} />
              </Button>
            </Tooltip>
            <ThreadPrimitive.If running>
              <ComposerPrimitive.Cancel asChild>
                <Button aria-label="Stop" color="danger" size="small">
                  <Square size={16} />
                </Button>
              </ComposerPrimitive.Cancel>
            </ThreadPrimitive.If>
            <ThreadPrimitive.If running={false}>
              <ComposerPrimitive.Send asChild>
                <Button aria-label="Submit" color="brand" size="small">
                  <Send size={16} />
                </Button>
              </ComposerPrimitive.Send>
            </ThreadPrimitive.If>
          </Flex>
        </ComposerPrimitive.Root>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {slotAboveComposer && <div className="shrink-0">{slotAboveComposer}</div>}
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
          rows={1}
          className="max-h-64 flex-1 resize-none border-0 bg-transparent p-density-sm text-sm outline-none disabled:cursor-not-allowed disabled:text-fg-disabled"
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
    </div>
  );
};

export const AssistantChatThread = ({
  disabled,
  placeholder,
  onReset,
  hideComposer,
  slotAboveComposer,
  emptyState,
  composerVariant,
  contentClassName,
  composerContainerClassName,
  viewportClassName,
  assistantMessageMetricsById,
}: AssistantChatThreadProps) => {
  // Playground centers the conversation + composer in a single reading column
  // so it doesn't stretch across a wide panel.
  const isPlayground = composerVariant === 'playground';
  const playgroundColumn = isPlayground ? 'mx-auto w-full max-w-3xl' : undefined;
  const AssistantMessage = createAssistantMessage(assistantMessageMetricsById);

  return (
    <ThreadPrimitive.Root className="flex h-full w-full flex-col" role="log">
      <ThreadPrimitive.Viewport
        className={cn('relative flex min-h-0 flex-1 flex-col overflow-y-auto', viewportClassName)}
      >
        <Stack
          gap="density-md"
          className={cn('min-h-full w-full', playgroundColumn, contentClassName)}
        >
          <ThreadPrimitive.Empty>
            <ChatEmptyState
              className="h-full min-h-[250px] w-full"
              slotHeading={emptyState?.slotHeading}
              slotSubheading={emptyState?.slotSubheading}
            />
          </ThreadPrimitive.Empty>
          <ThreadPrimitive.Messages
            components={{
              AssistantMessage,
              UserMessage,
              SystemMessage: AssistantMessage,
            }}
          />
        </Stack>
        <ThreadPrimitive.ScrollToBottom className="sticky bottom-density-sm self-center rounded border border-base bg-surface-raised px-density-sm py-density-xs text-sm shadow disabled:hidden">
          Scroll to bottom
        </ThreadPrimitive.ScrollToBottom>
      </ThreadPrimitive.Viewport>
      {!hideComposer && (
        <Flex className={cn('w-full', composerContainerClassName)}>
          <div className={cn('w-full', playgroundColumn)}>
            <AssistantComposer
              disabled={disabled}
              placeholder={placeholder}
              onReset={onReset}
              slotAboveComposer={slotAboveComposer}
              composerVariant={composerVariant}
            />
          </div>
        </Flex>
      )}
    </ThreadPrimitive.Root>
  );
};
