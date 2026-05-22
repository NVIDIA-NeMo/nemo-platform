// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ActionBarPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
  type TextMessagePartComponent,
  type ToolCallMessagePartProps,
  ThreadPrimitive,
} from '@assistant-ui/react';
import { MarkdownText } from '@nemo/common/src/components/AssistantChat/MarkdownText';
import { ToolCallShell } from '@nemo/common/src/components/AssistantChat/parts/ToolCallShell';
import { ToolOptionsMenu } from '@nemo/common/src/components/AssistantChat/ToolOptionsMenu';
import type { StudioToolRegistry } from '@nemo/common/src/components/AssistantChat/tools/types';
import { ChatEmptyState } from '@nemo/common/src/components/Chat/ChatEmptyState';
import {
  Banner,
  Button,
  Flex,
  Skeleton,
  Text,
  TextArea,
  Tooltip,
} from '@nvidia/foundations-react-core';
import cn from 'classnames';
import { Check, Copy, Pencil, RefreshCw, RotateCcw, Send, Square, Wrench, X } from 'lucide-react';

interface AssistantChatThreadProps {
  readonly disabled?: boolean;
  readonly placeholder: string;
  readonly onReset: () => void;
  readonly emptyState?: {
    readonly slotHeading?: string;
    readonly slotSubheading?: string;
  };
  readonly tools: StudioToolRegistry;
  readonly enabledToolNames: ReadonlySet<string>;
  readonly onToggleTool: (toolName: string, enabled: boolean) => void;
}

const AssistantChatTextPart: TextMessagePartComponent = ({ text, status }) => (
  <div className="relative">
    <MarkdownText content={text} />
    {status.type === 'running' ? (
      <span
        aria-hidden
        className="ml-density-2xs inline-block h-[1em] w-[2px] translate-y-[2px] animate-pulse bg-fg-base align-middle"
      />
    ) : null}
  </div>
);

const stringifyResult = (result: unknown): string => {
  if (result === undefined || result === null) return '';
  if (typeof result === 'string') return result;
  try {
    return JSON.stringify(result, null, 2);
  } catch {
    return String(result);
  }
};

const formatToolArgs = (argsText: string, args: unknown): string => {
  if (args && typeof args === 'object' && Object.keys(args).length > 0) {
    try {
      return JSON.stringify(args, null, 2);
    } catch {
      // fall through to argsText
    }
  }
  return argsText ?? '';
};

const FallbackToolCallPart = (props: ToolCallMessagePartProps) => {
  const formattedArgs = formatToolArgs(props.argsText, props.args);
  const resultText = stringifyResult(props.result);

  return (
    <ToolCallShell
      icon={<Wrench size={14} aria-hidden />}
      label={props.toolName || 'Tool call'}
      toolName={props.toolName}
      status={props.status}
    >
      <div className="flex flex-col gap-density-xs px-density-sm py-density-sm">
        <div>
          <Text kind="label/regular/xs" className="text-fg-muted">
            Arguments
          </Text>
          <pre className="mt-density-2xs overflow-x-auto rounded bg-surface-sunken p-density-xs text-xs text-fg-base">
            {formattedArgs || '{}'}
          </pre>
        </div>
        {resultText ? (
          <div>
            <Text
              kind="label/regular/xs"
              className={props.isError ? 'text-fg-status-warning' : 'text-fg-muted'}
            >
              {props.isError ? 'Error' : 'Result'}
            </Text>
            <pre className="mt-density-2xs overflow-x-auto rounded bg-surface-sunken p-density-xs text-xs text-fg-base">
              {resultText}
            </pre>
          </div>
        ) : null}
      </div>
    </ToolCallShell>
  );
};

const buildByNameRenderers = (tools: StudioToolRegistry) => {
  const byName: Record<string, NonNullable<(typeof tools)[number]['Render']>> = {};
  for (const tool of tools) {
    if (tool.Render) byName[tool.name] = tool.Render;
  }
  return byName;
};

interface AssistantChatMessageContentProps {
  readonly tools: StudioToolRegistry;
}

const AssistantChatMessageContent = ({ tools }: AssistantChatMessageContentProps) => (
  <>
    <MessagePrimitive.Parts
      components={{
        Text: AssistantChatTextPart,
        tools: {
          by_name: buildByNameRenderers(tools),
          Fallback: FallbackToolCallPart,
        },
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
  'flex cursor-pointer size-7 items-center justify-center rounded text-base bg-transparent hover:bg-surface-sunken disabled:cursor-not-allowed disabled:opacity-50';

const CopyAction = () => (
  <Tooltip slotContent="Copy message">
    <ActionBarPrimitive.Copy aria-label="Copy message" className={ACTION_BUTTON_CLASS}>
      <MessagePrimitive.If copied>
        <Check size={14} />
      </MessagePrimitive.If>
      <MessagePrimitive.If copied={false}>
        <Copy size={14} />
      </MessagePrimitive.If>
    </ActionBarPrimitive.Copy>
  </Tooltip>
);

interface MessageRowProps {
  readonly tools: StudioToolRegistry;
}

const AssistantMessage = ({ tools }: MessageRowProps) => (
  <MessagePrimitive.Root
    data-testid="assistant-chat-message"
    data-testspeaker="assistant"
    className="group/message flex w-full flex-col items-start gap-density-xs"
  >
    <div className="w-full max-w-[min(100%,72ch)] whitespace-pre-wrap">
      <AssistantChatMessageContent tools={tools} />
    </div>
    <MessagePrimitive.If last>
      <ThreadPrimitive.If running>
        <Skeleton className="h-density-4 w-32" data-testid="assistant-chat-skeleton" />
      </ThreadPrimitive.If>
    </MessagePrimitive.If>
    <ActionBarPrimitive.Root
      hideWhenRunning
      className={cn(
        'flex h-7 gap-density-2xs opacity-0 transition-opacity duration-150',
        'group-hover/message:opacity-100 group-focus-within/message:opacity-100',
        '[@media(hover:none)]:opacity-100'
      )}
    >
      <Tooltip slotContent="Regenerate response">
        <ActionBarPrimitive.Reload aria-label="Regenerate response" className={ACTION_BUTTON_CLASS}>
          <RefreshCw size={14} />
        </ActionBarPrimitive.Reload>
      </Tooltip>
      <CopyAction />
    </ActionBarPrimitive.Root>
  </MessagePrimitive.Root>
);

const UserMessage = ({ tools }: MessageRowProps) => (
  <MessagePrimitive.Root
    data-testid="assistant-chat-message"
    data-testspeaker="user"
    className="group/message flex w-full flex-col items-end gap-density-xs whitespace-pre-wrap"
  >
    <div className="max-w-[80%] rounded-xl rounded-br-none bg-surface-overlay px-density-md py-density-sm">
      <AssistantChatMessageContent tools={tools} />
    </div>
    <ActionBarPrimitive.Root
      hideWhenRunning
      className={cn(
        'flex h-7 gap-density-2xs opacity-0 transition-opacity duration-150',
        'group-hover/message:opacity-100 group-focus-within/message:opacity-100',
        '[@media(hover:none)]:opacity-100'
      )}
    >
      <Tooltip slotContent="Edit message">
        <ActionBarPrimitive.Edit aria-label="Edit message" className={ACTION_BUTTON_CLASS}>
          <Pencil size={14} />
        </ActionBarPrimitive.Edit>
      </Tooltip>
      <CopyAction />
    </ActionBarPrimitive.Root>
  </MessagePrimitive.Root>
);

const UserEditComposer = () => (
  <MessagePrimitive.Root
    data-testid="assistant-chat-edit-composer"
    className="w-full max-w-[80%] self-end rounded-xl rounded-br-none bg-surface-overlay px-density-md py-density-sm"
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
            className="max-h-64 w-full"
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
                    className="flex size-8 cursor-pointer items-center justify-center rounded border border-base bg-surface-raised hover:bg-surface-sunken disabled:cursor-not-allowed disabled:opacity-50"
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

interface AssistantComposerProps {
  readonly disabled?: boolean;
  readonly placeholder: string;
  readonly onReset: () => void;
  readonly tools: StudioToolRegistry;
  readonly enabledToolNames: ReadonlySet<string>;
  readonly onToggleTool: (toolName: string, enabled: boolean) => void;
}

const AssistantComposer = ({
  disabled,
  placeholder,
  onReset,
  tools,
  enabledToolNames,
  onToggleTool,
}: AssistantComposerProps) => (
  <ComposerPrimitive.Root className="flex items-end gap-density-xs rounded-lg border border-base bg-surface-base p-density-xs focus-within:border-fg-link">
    <ComposerPrimitive.Input
      aria-label="Task prompt"
      addAttachmentOnPaste={false}
      disabled={disabled}
      placeholder={placeholder}
      submitMode="enter"
      className="max-h-64 min-h-14 flex-1 resize-none border-0 bg-transparent p-density-sm text-sm outline-none disabled:cursor-not-allowed disabled:text-fg-disabled"
    />
    <div className="flex items-end gap-density-xs self-end pb-density-2xs">
      <ToolOptionsMenu
        tools={tools}
        enabled={enabledToolNames}
        onToggle={onToggleTool}
        disabled={disabled}
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
    </div>
  </ComposerPrimitive.Root>
);

export const AssistantChatThread = ({
  disabled,
  placeholder,
  onReset,
  emptyState,
  tools,
  enabledToolNames,
  onToggleTool,
}: AssistantChatThreadProps) => {
  const Assistant = () => <AssistantMessage tools={tools} />;
  const User = () => <UserMessage tools={tools} />;
  return (
    <ThreadPrimitive.Root className="flex h-full w-full flex-col gap-density-sm" role="log">
      <ThreadPrimitive.Viewport className="relative flex min-h-0 flex-1 flex-col gap-density-md overflow-y-auto pr-density-xs">
        <ThreadPrimitive.Empty>
          <ChatEmptyState
            className="h-full min-h-[250px] w-full"
            slotHeading={emptyState?.slotHeading}
            slotSubheading={emptyState?.slotSubheading}
          />
        </ThreadPrimitive.Empty>
        <ThreadPrimitive.Messages
          components={{
            AssistantMessage: Assistant,
            UserMessage: User,
            UserEditComposer,
            SystemMessage: Assistant,
          }}
        />
        <ThreadPrimitive.ScrollToBottom className="sticky bottom-density-sm self-center rounded-lg border border-base bg-surface-raised px-density-sm py-density-xs text-sm shadow-md disabled:hidden">
          Scroll to bottom
        </ThreadPrimitive.ScrollToBottom>
      </ThreadPrimitive.Viewport>
      <AssistantComposer
        disabled={disabled}
        placeholder={placeholder}
        onReset={onReset}
        tools={tools}
        enabledToolNames={enabledToolNames}
        onToggleTool={onToggleTool}
      />
    </ThreadPrimitive.Root>
  );
};
