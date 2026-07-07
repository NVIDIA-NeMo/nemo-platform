// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ToolCallMessagePartComponent } from '@assistant-ui/react';
import { MessageContent } from '@nemo/common/src/components/Chat/MessageContent';
import { Text } from '@nvidia/foundations-react-core';
import { ClaudeCodeStudioLink } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeStudioLink';
import { JobProgressToolCall } from '@studio/routes/agents/ClaudeCodeChatRoute/JobProgressToolCall';
import { CollapsedThinkingToolCall } from '@studio/routes/agents/ClaudeCodeChatRoute/toolCall/CollapsedThinkingToolCall';
import { TOOL_LABELS } from '@studio/routes/agents/ClaudeCodeChatRoute/toolCall/constants';
import { FileChangeToolCallCard } from '@studio/routes/agents/ClaudeCodeChatRoute/toolCall/FileChangeToolCallCard';
import {
  formatSubtleToolMessage,
  getFileChangeSummary,
  getStringArg,
  getSubtleToolDetail,
  getSubtleToolGroupActions,
  getSubtleToolIcon,
  getSubtleToolMessage,
  getToolSummary,
} from '@studio/routes/agents/ClaudeCodeChatRoute/toolCall/helpers';
import { SubtleToolCallRow } from '@studio/routes/agents/ClaudeCodeChatRoute/toolCall/SubtleToolCallRow';
import {
  CLAUDE_CODE_COLLAPSED_STUDIO_DETAILS_TOOL_NAME,
  CLAUDE_CODE_COLLAPSED_THINKING_TOOL_NAME,
  CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME,
  CLAUDE_CODE_WORK_DETAILS_LABEL,
  isClaudeCodeJobProgressToolName,
  toClaudeCodeToolArgs,
  type ClaudeCodeToolArgs,
} from '@studio/routes/agents/ClaudeCodeChatRoute/toolParts';
import { ChevronRight, ClipboardList } from 'lucide-react';

interface ClaudeCodeToolCallPartContentProps {
  readonly args: ClaudeCodeToolArgs;
  readonly argsText: string;
  readonly toolName: string;
}

interface CollapsedStudioDetailsTextPart {
  readonly text: string;
  readonly type: 'text';
}

interface CollapsedStudioDetailsToolPart {
  readonly args: ClaudeCodeToolArgs;
  readonly argsText: string;
  readonly toolCallId: string;
  readonly toolName: string;
  readonly type: 'tool-call';
}

type CollapsedStudioDetailsPart = CollapsedStudioDetailsTextPart | CollapsedStudioDetailsToolPart;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const getCollapsedStudioDetailsParts = (
  args: ClaudeCodeToolArgs
): readonly CollapsedStudioDetailsPart[] => {
  const parts = args.parts;
  if (!Array.isArray(parts)) return [];

  return parts
    .map((part): CollapsedStudioDetailsPart | undefined => {
      if (!isRecord(part)) return undefined;

      if (part.type === 'text' && typeof part.text === 'string' && part.text.trim()) {
        return { type: 'text', text: part.text };
      }

      if (
        part.type === 'tool-call' &&
        typeof part.toolName === 'string' &&
        typeof part.toolCallId === 'string'
      ) {
        const toolArgs = isRecord(part.args) ? toClaudeCodeToolArgs(part.args) : {};
        return {
          type: 'tool-call',
          args: toolArgs,
          argsText: typeof part.argsText === 'string' ? part.argsText : JSON.stringify(toolArgs),
          toolCallId: part.toolCallId,
          toolName: part.toolName,
        };
      }

      return undefined;
    })
    .filter((part): part is CollapsedStudioDetailsPart => part !== undefined);
};

const CollapsedStudioDetailsText = ({ text }: { readonly text: string }) => (
  <MessageContent content={text} markdownLinkComponent={ClaudeCodeStudioLink} />
);

const CollapsedStudioDetailsPartContent = ({
  part,
}: {
  readonly part: CollapsedStudioDetailsPart;
}) => {
  if (part.type === 'text') return <CollapsedStudioDetailsText text={part.text} />;

  return (
    <ClaudeCodeToolCallPartContent
      args={part.args}
      argsText={part.argsText}
      toolName={part.toolName}
    />
  );
};

const CollapsedStudioDetailsToolCall = ({ args }: { readonly args: ClaudeCodeToolArgs }) => {
  const storedLabel = getStringArg(args, ['label']);
  const label =
    !storedLabel || storedLabel.toLowerCase() === 'worked for unknown'
      ? CLAUDE_CODE_WORK_DETAILS_LABEL
      : storedLabel;
  const parts = getCollapsedStudioDetailsParts(args);
  if (!parts.length) return null;

  return (
    <Text asChild kind="body/regular/sm">
      <details
        className="group/studio-details my-density-xs max-w-full text-gray-500 dark:text-gray-400"
        data-testid="claude-code-collapsed-studio-details"
      >
        <summary className="inline-flex cursor-pointer list-none items-center gap-density-xs marker:hidden">
          <ChevronRight
            aria-hidden
            className="size-3 shrink-0 transition-transform group-open/studio-details:rotate-90"
          />
          <ClipboardList aria-hidden className="size-3.5 shrink-0" />
          <span>{label}</span>
        </summary>
        <div
          className="mt-density-xs space-y-density-xs border-l border-base pl-density-md text-secondary"
          data-testid="claude-code-collapsed-studio-details-content"
        >
          {parts.map((part, index) => (
            <CollapsedStudioDetailsPartContent
              key={`${part.type}-${part.type === 'text' ? part.text.slice(0, 24) : part.toolCallId}-${index}`}
              part={part}
            />
          ))}
        </div>
      </details>
    </Text>
  );
};

const ClaudeCodeToolCallPartContent = ({
  args,
  argsText,
  toolName,
}: ClaudeCodeToolCallPartContentProps) => {
  if (toolName === CLAUDE_CODE_COLLAPSED_STUDIO_DETAILS_TOOL_NAME) {
    return <CollapsedStudioDetailsToolCall args={args} />;
  }

  if (toolName === CLAUDE_CODE_COLLAPSED_THINKING_TOOL_NAME) {
    const text = getStringArg(args, ['text']);
    return text ? <CollapsedThinkingToolCall text={text} /> : null;
  }

  if (isClaudeCodeJobProgressToolName(toolName)) {
    return <JobProgressToolCall args={args} />;
  }

  if (toolName === CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME) {
    const subtleActions = getSubtleToolGroupActions(args);
    return subtleActions.length ? <SubtleToolCallRow actions={subtleActions} /> : null;
  }

  const subtleMessage = getSubtleToolMessage(toolName, args);
  if (subtleMessage) {
    return (
      <SubtleToolCallRow
        actions={[
          {
            detail: getSubtleToolDetail(toolName, args, subtleMessage),
            Icon: getSubtleToolIcon(toolName),
            message: subtleMessage,
            toolCallId: toolName,
            toolName,
          },
        ]}
      />
    );
  }

  if (toolName === 'Write' || toolName === 'Edit' || toolName === 'MultiEdit') {
    const fileChangeSummary = getFileChangeSummary(toolName, args, argsText);
    if (fileChangeSummary) {
      return <FileChangeToolCallCard summary={fileChangeSummary} />;
    }
  }

  const label = TOOL_LABELS[toolName] ?? toolName;
  const fallbackMessage = formatSubtleToolMessage(
    `Used ${label}`,
    getToolSummary(toolName, args),
    `Used ${label}`
  );
  return (
    <SubtleToolCallRow
      actions={[
        {
          detail: getSubtleToolDetail(toolName, args, fallbackMessage),
          Icon: getSubtleToolIcon(toolName),
          message: fallbackMessage,
          toolCallId: toolName,
          toolName,
        },
      ]}
    />
  );
};

export const ClaudeCodeToolCallPart: ToolCallMessagePartComponent<ClaudeCodeToolArgs, unknown> = ({
  args,
  argsText,
  toolName,
}) => <ClaudeCodeToolCallPartContent args={args} argsText={argsText} toolName={toolName} />;
