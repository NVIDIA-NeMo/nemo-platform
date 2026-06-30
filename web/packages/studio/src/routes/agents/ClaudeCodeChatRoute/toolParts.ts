// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ThreadAssistantMessagePart, ThreadMessageLike } from '@assistant-ui/react';
import {
  CLAUDE_CODE_JOB_PROGRESS_MCP_TOOL_NAME,
  CLAUDE_CODE_JOB_PROGRESS_TOOL_NAME,
} from '@studio/routes/agents/ClaudeCodeChatRoute/jobProgressConsts';

type ClaudeCodeToolCallPart = Extract<ThreadAssistantMessagePart, { type: 'tool-call' }>;
export type ClaudeCodeToolArgs = ClaudeCodeToolCallPart['args'];
type ClaudeCodeToolArgValue = ClaudeCodeToolArgs[string];

export const CLAUDE_CODE_COLLAPSED_THINKING_TOOL_NAME = 'ClaudeCodeCollapsedThinking';
export const CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME = 'ClaudeCodeSubtleToolGroup';

const FILE_CHANGE_TOOL_CALL_NAMES = new Set(['Edit', 'MultiEdit', 'Write']);

export const isClaudeCodeJobProgressToolName = (toolName: string): boolean =>
  toolName === CLAUDE_CODE_JOB_PROGRESS_TOOL_NAME ||
  toolName === CLAUDE_CODE_JOB_PROGRESS_MCP_TOOL_NAME;

export const isClaudeCodeSubtleToolCallName = (toolName: string): boolean =>
  toolName !== CLAUDE_CODE_COLLAPSED_THINKING_TOOL_NAME &&
  toolName !== CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME &&
  !FILE_CHANGE_TOOL_CALL_NAMES.has(toolName) &&
  !isClaudeCodeJobProgressToolName(toolName);

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const toClaudeCodeToolArgValue = (value: unknown): ClaudeCodeToolArgValue | undefined => {
  if (value === null) return value;
  if (typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') return Number.isFinite(value) ? value : undefined;

  if (Array.isArray(value)) {
    return value
      .map(toClaudeCodeToolArgValue)
      .filter((item): item is ClaudeCodeToolArgValue => item !== undefined);
  }

  if (isRecord(value)) return toClaudeCodeToolArgs(value);

  return undefined;
};

export const toClaudeCodeToolArgs = (input: unknown): ClaudeCodeToolArgs => {
  if (!isRecord(input)) return {};

  const args: Record<string, ClaudeCodeToolArgValue> = {};
  for (const [key, value] of Object.entries(input)) {
    const nextValue = toClaudeCodeToolArgValue(value);
    if (nextValue !== undefined) args[key] = nextValue;
  }

  return args;
};

export const createClaudeCodeToolCallPart = ({
  input,
  toolCallId,
  toolName,
}: {
  input: unknown;
  toolCallId: string;
  toolName: string;
}): ThreadAssistantMessagePart => {
  const args = toClaudeCodeToolArgs(input);
  return {
    type: 'tool-call',
    toolCallId,
    toolName,
    args,
    argsText: JSON.stringify(args),
  };
};

const createClaudeCodeCollapsedThinkingPart = (text: string): ThreadAssistantMessagePart => {
  const args = toClaudeCodeToolArgs({ text });

  return {
    type: 'tool-call',
    toolCallId: 'claude-code-collapsed-thinking',
    toolName: CLAUDE_CODE_COLLAPSED_THINKING_TOOL_NAME,
    args,
    argsText: JSON.stringify(args),
  };
};

interface ClaudeCodeSubtleToolAction {
  readonly args: ClaudeCodeToolArgs;
  readonly toolCallId: string;
  readonly toolName: string;
}

interface ClaudeCodeSubtleToolPartGroup {
  readonly actions: readonly ClaudeCodeSubtleToolAction[];
  readonly part: ThreadAssistantMessagePart;
}

const getGroupedSubtleToolActions = (
  part: ClaudeCodeToolCallPart
): readonly ClaudeCodeSubtleToolAction[] => {
  const actions = part.args.actions;
  if (!Array.isArray(actions)) return [];

  return actions
    .filter(isRecord)
    .map((action): ClaudeCodeSubtleToolAction | undefined => {
      const toolCallId = typeof action.toolCallId === 'string' ? action.toolCallId : undefined;
      const toolName = typeof action.toolName === 'string' ? action.toolName : undefined;
      if (!toolCallId || !toolName || !isClaudeCodeSubtleToolCallName(toolName)) return undefined;

      return {
        args: isRecord(action.args) ? toClaudeCodeToolArgs(action.args) : {},
        toolCallId,
        toolName,
      };
    })
    .filter((action): action is ClaudeCodeSubtleToolAction => action !== undefined);
};

const getSubtleToolActions = (
  part: ThreadAssistantMessagePart
): readonly ClaudeCodeSubtleToolAction[] | undefined => {
  if (part.type !== 'tool-call') return undefined;

  if (part.toolName === CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME) {
    const actions = getGroupedSubtleToolActions(part);
    return actions.length ? actions : undefined;
  }

  if (!isClaudeCodeSubtleToolCallName(part.toolName)) return undefined;

  return [
    {
      args: part.args,
      toolCallId: part.toolCallId,
      toolName: part.toolName,
    },
  ];
};

const isEmptyAssistantTextPart = (part: ThreadAssistantMessagePart): boolean =>
  part.type === 'text' && part.text.trim().length === 0;

const isClaudeCodeSubtleToolCallPart = (part: ThreadAssistantMessagePart): boolean =>
  getSubtleToolActions(part) !== undefined;

const createClaudeCodeSubtleToolGroupPart = (
  actions: readonly ClaudeCodeSubtleToolAction[]
): ThreadAssistantMessagePart => {
  const firstAction = actions[0]!;
  const lastAction = actions[actions.length - 1]!;
  const args = toClaudeCodeToolArgs({
    actions: actions.map((action) => ({
      args: action.args,
      toolCallId: action.toolCallId,
      toolName: action.toolName,
    })),
  });

  return {
    type: 'tool-call',
    toolCallId: `claude-code-subtle-tools-${firstAction.toolCallId}-${lastAction.toolCallId}`,
    toolName: CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME,
    args,
    argsText: JSON.stringify(args),
  };
};

const splitTextParagraphs = (text: string): readonly string[] =>
  text
    .trim()
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);

const getCollapsedTextParts = (
  parts: readonly ThreadAssistantMessagePart[],
  lastToolIndex: number
): {
  readonly collapsedText: string | undefined;
  readonly summaryText: string | undefined;
} => {
  const thinkingTextParts: string[] = [];
  const trailingTextParts: string[] = [];

  parts.forEach((part, index) => {
    if (part.type !== 'text') return;

    const text = part.text.trim();
    if (!text) return;

    if (index > lastToolIndex) {
      trailingTextParts.push(text);
    } else {
      thinkingTextParts.push(text);
    }
  });

  const trailingParagraphs = splitTextParagraphs(trailingTextParts.join('\n\n'));
  const summaryParagraphs = trailingParagraphs.slice(-2);
  const collapsedTrailingParagraphs = trailingParagraphs.slice(0, -2);
  const collapsedParagraphs = splitTextParagraphs(
    [...thinkingTextParts, collapsedTrailingParagraphs.join('\n\n')].filter(Boolean).join('\n\n')
  );

  return {
    collapsedText: collapsedParagraphs.length ? collapsedParagraphs.join('\n\n') : undefined,
    summaryText: summaryParagraphs.length ? summaryParagraphs.join('\n\n') : undefined,
  };
};

export const getClaudeCodeCompletedMessageParts = (
  parts: readonly ThreadAssistantMessagePart[]
): readonly ThreadAssistantMessagePart[] => {
  const completedParts: ThreadAssistantMessagePart[] = [];
  let lastToolIndex = -1;

  parts.forEach((part, index) => {
    if (part.type === 'tool-call') {
      completedParts.push(part);
      lastToolIndex = index;
    }
  });

  if (lastToolIndex < 0) return parts;

  const { collapsedText, summaryText } = getCollapsedTextParts(parts, lastToolIndex);
  if (collapsedText) completedParts.unshift(createClaudeCodeCollapsedThinkingPart(collapsedText));
  for (const part of parts.slice(lastToolIndex + 1)) {
    if (part.type === 'text') continue;
    completedParts.push(part);
  }
  if (summaryText) completedParts.push({ type: 'text', text: summaryText });

  return completedParts;
};

export const groupConsecutiveClaudeCodeSubtleToolCalls = (
  parts: readonly ThreadAssistantMessagePart[]
): readonly ThreadAssistantMessagePart[] => {
  const groupedParts: ThreadAssistantMessagePart[] = [];
  let currentGroup: ClaudeCodeSubtleToolPartGroup[] = [];

  const flushGroup = () => {
    if (!currentGroup.length) return;

    const actions = currentGroup.flatMap((group) => group.actions);
    if (
      actions.length === 1 &&
      currentGroup.length === 1 &&
      currentGroup[0]!.part.type === 'tool-call' &&
      currentGroup[0]!.part.toolName !== CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME
    ) {
      groupedParts.push(currentGroup[0]!.part);
    } else {
      groupedParts.push(createClaudeCodeSubtleToolGroupPart(actions));
    }

    currentGroup = [];
  };

  for (const part of parts) {
    if (isEmptyAssistantTextPart(part)) continue;

    const actions = getSubtleToolActions(part);
    if (actions) {
      currentGroup.push({ actions, part });
      continue;
    }

    flushGroup();
    groupedParts.push(part);
  }

  flushGroup();
  return groupedParts;
};

const getToolOnlyAssistantMessageParts = (
  message: ThreadMessageLike
): readonly ThreadAssistantMessagePart[] | undefined => {
  if (message.role !== 'assistant' || !Array.isArray(message.content)) return undefined;

  const visibleParts = message.content.filter((part) => !isEmptyAssistantTextPart(part));
  if (!visibleParts.length || !visibleParts.every(isClaudeCodeSubtleToolCallPart)) return undefined;
  return visibleParts;
};

export const mergeConsecutiveClaudeCodeSubtleToolMessages = (
  messages: readonly ThreadMessageLike[]
): readonly ThreadMessageLike[] => {
  const mergedMessages: ThreadMessageLike[] = [];
  let pendingMessage: ThreadMessageLike | undefined;
  let pendingParts: ThreadAssistantMessagePart[] = [];

  const flushPendingMessage = () => {
    if (!pendingMessage) return;

    mergedMessages.push({
      ...pendingMessage,
      content: groupConsecutiveClaudeCodeSubtleToolCalls(pendingParts),
    });
    pendingMessage = undefined;
    pendingParts = [];
  };

  for (const message of messages) {
    const toolOnlyParts = getToolOnlyAssistantMessageParts(message);
    if (!toolOnlyParts) {
      flushPendingMessage();
      mergedMessages.push(message);
      continue;
    }

    if (!pendingMessage) {
      pendingMessage = message;
    } else {
      pendingMessage = {
        ...pendingMessage,
        status: message.status ?? pendingMessage.status,
      };
    }
    pendingParts.push(...toolOnlyParts);
  }

  flushPendingMessage();
  return mergedMessages;
};
