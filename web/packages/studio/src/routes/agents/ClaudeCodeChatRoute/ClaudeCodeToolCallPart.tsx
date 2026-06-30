// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ToolCallMessagePartComponent } from '@assistant-ui/react';
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
  CLAUDE_CODE_COLLAPSED_THINKING_TOOL_NAME,
  CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME,
  isClaudeCodeJobProgressToolName,
  type ClaudeCodeToolArgs,
} from '@studio/routes/agents/ClaudeCodeChatRoute/toolParts';

interface ClaudeCodeToolCallPartContentProps {
  readonly args: ClaudeCodeToolArgs;
  readonly argsText: string;
  readonly isRunning?: boolean;
  readonly toolName: string;
}

const ClaudeCodeToolCallPartContent = ({
  args,
  argsText,
  toolName,
  isRunning = false,
}: ClaudeCodeToolCallPartContentProps) => {
  if (toolName === CLAUDE_CODE_COLLAPSED_THINKING_TOOL_NAME) {
    const text = getStringArg(args, ['text']);
    return text ? <CollapsedThinkingToolCall text={text} /> : null;
  }

  if (isClaudeCodeJobProgressToolName(toolName)) {
    return <JobProgressToolCall args={args} />;
  }

  if (toolName === CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME) {
    const subtleActions = getSubtleToolGroupActions(args);
    return subtleActions.length ? (
      <SubtleToolCallRow actions={subtleActions} isRunning={isRunning} />
    ) : null;
  }

  const subtleMessage = getSubtleToolMessage(toolName, args);
  if (subtleMessage) {
    return (
      <SubtleToolCallRow
        isRunning={isRunning}
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
      return <FileChangeToolCallCard isRunning={isRunning} summary={fileChangeSummary} />;
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
      isRunning={isRunning}
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
  status,
  toolName,
}) => (
  <ClaudeCodeToolCallPartContent
    args={args}
    argsText={argsText}
    isRunning={status.type === 'running'}
    toolName={toolName}
  />
);
