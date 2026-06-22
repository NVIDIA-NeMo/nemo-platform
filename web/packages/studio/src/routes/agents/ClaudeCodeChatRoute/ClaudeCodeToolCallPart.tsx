// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ToolCallMessagePartComponent } from '@assistant-ui/react';
import { Text } from '@nvidia/foundations-react-core';
import { JobProgressToolCall } from '@studio/routes/agents/ClaudeCodeChatRoute/JobProgressToolCall';
import {
  CLAUDE_CODE_COLLAPSED_THINKING_TOOL_NAME,
  CLAUDE_CODE_SUBTLE_TOOL_GROUP_NAME,
  isClaudeCodeJobProgressToolName,
  isClaudeCodeSubtleToolCallName,
  toClaudeCodeToolArgs,
  type ClaudeCodeToolArgs,
} from '@studio/routes/agents/ClaudeCodeChatRoute/toolParts';
import cn from 'classnames';
import {
  CheckSquare,
  ChevronRight,
  CircleHelp,
  ClipboardList,
  Command,
  FilePenLine,
  FilePlus2,
  FileText,
  Globe,
  ListTree,
  Search,
  Terminal,
  type LucideIcon,
} from 'lucide-react';

const TOOL_LABELS: Record<string, string> = {
  Bash: 'Run command',
  Edit: 'Edit file',
  Glob: 'Find files',
  Grep: 'Search text',
  LS: 'List directory',
  MultiEdit: 'Edit file',
  Read: 'Read file',
  TodoWrite: 'Update todos',
  WebFetch: 'Fetch URL',
  WebSearch: 'Search web',
  Write: 'Write file',
};

const TOOL_ICONS: Record<string, LucideIcon> = {
  Bash: Terminal,
  Edit: FilePenLine,
  Glob: Search,
  Grep: Search,
  LS: ListTree,
  MultiEdit: FilePenLine,
  Read: FileText,
  TodoWrite: CheckSquare,
  WebFetch: Globe,
  WebSearch: Search,
  Write: FilePenLine,
};

const CODE_BLOCK_SURFACE_CLASS = 'bg-gray-050 dark:bg-gray-900';
const FILE_CHANGE_ADDITION_CLASS = 'text-feedback-success';
const FILE_CHANGE_DELETION_CLASS = 'text-feedback-danger';
const SUBTLE_MESSAGE_MAX_LENGTH = 160;
const RUNNING_TOOL_CALL_CLASS = 'claude-code-tool-call-running';

const SUBTLE_TOOL_ICONS: Record<string, LucideIcon> = {
  AskUserQuestion: CircleHelp,
  Bash: Command,
  FindFiles: Search,
  Grep: Search,
  Read: FileText,
  TaskCreate: ClipboardList,
  TaskUpdate: ClipboardList,
  ToolSearch: Search,
};

interface SubtleToolAction {
  readonly detail: string;
  readonly details?: readonly string[];
  readonly Icon: LucideIcon;
  readonly message: string;
  readonly title?: string;
  readonly toolCallId: string;
  readonly toolName: string;
}

const getStringArg = (args: ClaudeCodeToolArgs, keys: string[]): string | undefined => {
  for (const key of keys) {
    const value = args[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return undefined;
};

const getRawStringArg = (args: Record<string, unknown>, keys: string[]): string | undefined => {
  for (const key of keys) {
    const value = args[key];
    if (typeof value === 'string') return value;
  }
  return undefined;
};

const getToolSummary = (toolName: string, args: ClaudeCodeToolArgs): string | undefined => {
  switch (toolName) {
    case 'Bash':
      return getStringArg(args, ['command']);
    case 'Edit':
    case 'MultiEdit':
    case 'Read':
    case 'Write':
      return getStringArg(args, ['file_path', 'path']);
    case 'Glob':
      return getStringArg(args, ['pattern']);
    case 'Grep': {
      const pattern = getStringArg(args, ['pattern']);
      const path = getStringArg(args, ['path']);
      return [pattern, path].filter(Boolean).join(' in ') || undefined;
    }
    case 'LS':
      return getStringArg(args, ['path']);
    case 'TodoWrite': {
      const todos = args.todos;
      return Array.isArray(todos) ? `${todos.length} todos` : undefined;
    }
    case 'WebFetch':
      return getStringArg(args, ['url']);
    case 'WebSearch':
      return getStringArg(args, ['query']);
    default:
      return getStringArg(args, ['command', 'file_path', 'path', 'pattern', 'query', 'url']);
  }
};

const compactSubtleDetail = (detail: string | undefined): string | undefined => {
  const compacted = detail?.replace(/\s+/g, ' ').trim();
  if (!compacted) return undefined;
  if (compacted.length <= SUBTLE_MESSAGE_MAX_LENGTH) return compacted;
  return `${compacted.slice(0, SUBTLE_MESSAGE_MAX_LENGTH - 3).trimEnd()}...`;
};

const formatSubtleToolMessage = (
  action: string,
  detail: string | undefined,
  fallback: string
): string => {
  const compactedDetail = compactSubtleDetail(detail);
  return compactedDetail ? `${action} ${compactedDetail}` : fallback;
};

const getSubtleToolIcon = (toolName: string): LucideIcon =>
  SUBTLE_TOOL_ICONS[toolName] ?? TOOL_ICONS[toolName] ?? Terminal;

const getRepeatedSubtleToolMessage = (toolName: string, count: number): string => {
  switch (toolName) {
    case 'AskUserQuestion':
      return `Asked ${count} questions`;
    case 'Bash':
      return `Ran ${count} commands`;
    case 'FindFiles':
      return `Searched files ${count} times`;
    case 'Glob':
      return `Found files ${count} times`;
    case 'Grep':
      return `Searched text ${count} times`;
    case 'LS':
      return `Listed ${count} directories`;
    case 'Read':
      return `Read ${count} files`;
    case 'TaskCreate':
      return `Created ${count} tasks`;
    case 'TaskUpdate':
      return `Updated ${count} tasks`;
    case 'TodoWrite':
      return `Updated todos ${count} times`;
    case 'ToolSearch':
      return `Searched tools ${count} times`;
    case 'WebFetch':
      return `Fetched ${count} URLs`;
    case 'WebSearch':
      return `Searched web ${count} times`;
    default: {
      const label = TOOL_LABELS[toolName] ?? toolName;
      return `Used ${label} ${count} times`;
    }
  }
};

const getFileName = (path: string): string => {
  const segments = path.split(/[\\/]/).filter(Boolean);
  return segments.at(-1) ?? path;
};

const getLineCount = (content: string): number => {
  if (!content) return 0;

  const normalized = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  const withoutTrailingNewline = normalized.endsWith('\n') ? normalized.slice(0, -1) : normalized;

  return withoutTrailingNewline.split('\n').length;
};

const getEditStats = (args: Record<string, unknown>): { additions: number; deletions: number } => ({
  additions: getLineCount(getRawStringArg(args, ['new_string']) ?? ''),
  deletions: getLineCount(getRawStringArg(args, ['old_string']) ?? ''),
});

const isToolArgsRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const splitCollapsedThinkingParagraphs = (text: string): readonly string[] =>
  text
    .trim()
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);

const getAskUserQuestionSummary = (args: ClaudeCodeToolArgs): string | undefined => {
  const questions = args.questions;
  const firstQuestion = Array.isArray(questions) ? questions.find(isToolArgsRecord) : undefined;
  return (
    getStringArg(args, ['question', 'prompt']) ??
    (firstQuestion
      ? getRawStringArg(firstQuestion, ['question', 'prompt', 'header'])?.trim()
      : undefined)
  );
};

interface FileChangeSummary {
  readonly action: 'Edited' | 'Wrote';
  readonly additions: number;
  readonly deletions: number;
  readonly path: string;
  readonly reviewContent: string;
}

const formatArgs = (args: ClaudeCodeToolArgs, argsText: string): string => {
  const trimmedArgsText = argsText.trim();
  if (trimmedArgsText && trimmedArgsText !== '{}') return trimmedArgsText;
  return JSON.stringify(args, null, 2);
};

const getFileChangeSummary = (
  toolName: string,
  args: ClaudeCodeToolArgs,
  argsText: string
): FileChangeSummary | undefined => {
  const path = getStringArg(args, ['file_path', 'path']);
  if (!path) return undefined;

  if (toolName === 'Write') {
    const content = getRawStringArg(args, ['content']);
    if (content === undefined) return undefined;

    return {
      action: 'Wrote',
      additions: getLineCount(content),
      deletions: 0,
      path,
      reviewContent: content,
    };
  }

  if (toolName === 'Edit') {
    return {
      action: 'Edited',
      ...getEditStats(args),
      path,
      reviewContent: formatArgs(args, argsText),
    };
  }

  if (toolName === 'MultiEdit') {
    const edits = args.edits;
    if (!Array.isArray(edits)) return undefined;

    const stats = edits.filter(isToolArgsRecord).reduce<{ additions: number; deletions: number }>(
      (total, edit) => {
        const editStats = getEditStats(edit);
        return {
          additions: total.additions + editStats.additions,
          deletions: total.deletions + editStats.deletions,
        };
      },
      { additions: 0, deletions: 0 }
    );

    return {
      action: 'Edited',
      ...stats,
      path,
      reviewContent: formatArgs(args, argsText),
    };
  }

  return undefined;
};

const getSubtleToolMessage = (toolName: string, args: ClaudeCodeToolArgs): string | undefined => {
  if (!isClaudeCodeSubtleToolCallName(toolName)) return undefined;

  if (toolName === 'AskUserQuestion') {
    return formatSubtleToolMessage('Asked', getAskUserQuestionSummary(args), 'Asked user question');
  }

  if (toolName === 'Bash') {
    return formatSubtleToolMessage(
      'Ran',
      getStringArg(args, ['description', 'command']),
      'Ran command'
    );
  }

  if (toolName === 'FindFiles') {
    return formatSubtleToolMessage(
      'Searched files',
      getStringArg(args, ['query', 'pattern', 'path']),
      'Searched files'
    );
  }

  if (toolName === 'Grep') {
    return formatSubtleToolMessage(
      'Searched text',
      getToolSummary(toolName, args),
      'Searched text'
    );
  }

  if (toolName === 'Glob') {
    return formatSubtleToolMessage('Found files', getToolSummary(toolName, args), 'Found files');
  }

  if (toolName === 'LS') {
    return formatSubtleToolMessage(
      'Listed directory',
      getToolSummary(toolName, args),
      'Listed directory'
    );
  }

  if (toolName === 'Read') {
    const path = getStringArg(args, ['file_path', 'path']);
    return path ? `Read ${getFileName(path)}` : 'Read file';
  }

  if (toolName === 'TaskCreate') {
    return formatSubtleToolMessage(
      'Created task',
      getStringArg(args, ['description', 'task', 'prompt', 'query']),
      'Created task'
    );
  }

  if (toolName === 'TaskUpdate') {
    return formatSubtleToolMessage(
      'Updated task',
      getStringArg(args, ['description', 'task', 'status']),
      'Updated task'
    );
  }

  if (toolName === 'TodoWrite') {
    return formatSubtleToolMessage(
      'Updated todos',
      getToolSummary(toolName, args),
      'Updated todos'
    );
  }

  if (toolName === 'ToolSearch') {
    return formatSubtleToolMessage(
      'Searched tools',
      getStringArg(args, ['query', 'pattern', 'name']),
      'Searched tools'
    );
  }

  if (toolName === 'WebFetch') {
    return formatSubtleToolMessage('Fetched URL', getToolSummary(toolName, args), 'Fetched URL');
  }

  if (toolName === 'WebSearch') {
    return formatSubtleToolMessage('Searched web', getToolSummary(toolName, args), 'Searched web');
  }

  const label = TOOL_LABELS[toolName] ?? toolName;
  return formatSubtleToolMessage(`Used ${label}`, getToolSummary(toolName, args), `Used ${label}`);
};

const getSubtleToolDetail = (
  toolName: string,
  args: ClaudeCodeToolArgs,
  message: string
): string => {
  if (toolName === 'AskUserQuestion') {
    return compactSubtleDetail(getAskUserQuestionSummary(args)) ?? message;
  }

  if (toolName === 'Bash') {
    return compactSubtleDetail(getStringArg(args, ['description', 'command'])) ?? message;
  }

  if (toolName === 'FindFiles') {
    return compactSubtleDetail(getStringArg(args, ['query', 'pattern', 'path'])) ?? message;
  }

  if (toolName === 'Read') {
    const path = getStringArg(args, ['file_path', 'path']);
    return path ? getFileName(path) : message;
  }

  if (toolName === 'TaskCreate') {
    return (
      compactSubtleDetail(getStringArg(args, ['description', 'task', 'prompt', 'query'])) ?? message
    );
  }

  if (toolName === 'TaskUpdate') {
    return compactSubtleDetail(getStringArg(args, ['description', 'task', 'status'])) ?? message;
  }

  if (toolName === 'ToolSearch') {
    return compactSubtleDetail(getStringArg(args, ['query', 'pattern', 'name'])) ?? message;
  }

  return compactSubtleDetail(getToolSummary(toolName, args)) ?? message;
};

const getSubtleToolGroupActions = (args: ClaudeCodeToolArgs): readonly SubtleToolAction[] => {
  const actions = args.actions;
  if (!Array.isArray(actions)) return [];

  return actions
    .filter(isToolArgsRecord)
    .map((action, index): SubtleToolAction | undefined => {
      const toolName = getRawStringArg(action, ['toolName'])?.trim();
      if (!toolName) return undefined;

      const actionArgs = isToolArgsRecord(action.args) ? toClaudeCodeToolArgs(action.args) : {};
      const message = getSubtleToolMessage(toolName, actionArgs);
      if (!message) return undefined;

      return {
        detail: getSubtleToolDetail(toolName, actionArgs, message),
        Icon: getSubtleToolIcon(toolName),
        message,
        toolCallId: getRawStringArg(action, ['toolCallId'])?.trim() ?? `${toolName}-${index}`,
        toolName,
      };
    })
    .filter((action): action is SubtleToolAction => action !== undefined);
};

const summarizeRepeatedSubtleToolActions = (
  actions: readonly SubtleToolAction[]
): readonly SubtleToolAction[] => {
  const groupedActions = new Map<string, SubtleToolAction[]>();

  for (const action of actions) {
    const existingActions = groupedActions.get(action.toolName);
    if (existingActions) {
      existingActions.push(action);
    } else {
      groupedActions.set(action.toolName, [action]);
    }
  }

  return Array.from(groupedActions.values()).map((group) => {
    if (group.length === 1) return group[0]!;

    const firstAction = group[0]!;
    return {
      ...firstAction,
      details: group.map((action) => action.detail),
      message: getRepeatedSubtleToolMessage(firstAction.toolName, group.length),
      title: group.map((action) => action.message).join(' | '),
      toolCallId: `${firstAction.toolCallId}-${group.length}`,
    };
  });
};

interface SubtleToolCallRowProps {
  readonly actions: readonly SubtleToolAction[];
  readonly isRunning?: boolean;
}

const SubtleToolCallRow = ({ actions, isRunning = false }: SubtleToolCallRowProps) => (
  <Text asChild kind="body/regular/sm">
    <div
      className={cn(
        'my-0.5 flex max-w-full flex-wrap items-center gap-x-density-sm gap-y-0 text-gray-400 dark:text-gray-400',
        isRunning && RUNNING_TOOL_CALL_CLASS
      )}
      data-testid="claude-code-tool-call-subtle"
      title={actions.map((action) => action.title ?? action.message).join(' | ')}
    >
      {summarizeRepeatedSubtleToolActions(actions).map((action, index) => {
        const Icon = action.Icon;
        const key = `${action.toolCallId}-${index}`;

        if (action.details?.length) {
          return (
            <details
              key={key}
              className="group/subtle max-w-full basis-full"
              data-testid="claude-code-tool-call-subtle-details"
            >
              <summary
                className="inline-flex cursor-pointer list-none items-center gap-density-xs marker:hidden"
                data-testid="claude-code-tool-call-subtle-action"
              >
                <ChevronRight
                  aria-hidden
                  className="size-3 shrink-0 transition-transform group-open/subtle:rotate-90"
                />
                <Icon
                  aria-hidden
                  className="size-3.5 shrink-0"
                  data-testid="claude-code-tool-call-subtle-icon"
                />
                <span className="min-w-0 truncate">{action.message}</span>
              </summary>
              <ul
                className="mt-0.5 max-w-full space-y-0.5 pl-7"
                data-testid="claude-code-tool-call-subtle-detail-list"
              >
                {action.details.map((detail, detailIndex) => (
                  <li
                    key={`${action.toolCallId}-${detailIndex}`}
                    className="min-w-0 truncate"
                    data-testid="claude-code-tool-call-subtle-detail-item"
                    title={detail}
                  >
                    {detail}
                  </li>
                ))}
              </ul>
            </details>
          );
        }

        return (
          <span
            key={key}
            className="inline-flex min-w-0 max-w-full basis-full items-center gap-density-xs"
            data-testid="claude-code-tool-call-subtle-action"
          >
            <Icon
              aria-hidden
              className="size-3.5 shrink-0"
              data-testid="claude-code-tool-call-subtle-icon"
            />
            <span className="min-w-0 truncate">{action.message}</span>
          </span>
        );
      })}
    </div>
  </Text>
);

const CollapsedThinkingToolCall = ({ text }: { readonly text: string }) => {
  const paragraphs = splitCollapsedThinkingParagraphs(text);
  if (!paragraphs.length) return null;

  return (
    <Text asChild kind="body/regular/sm">
      <details
        className="group/thinking my-density-xs max-w-full text-gray-500 dark:text-gray-400"
        data-testid="claude-code-collapsed-thinking"
      >
        <summary className="inline-flex cursor-pointer list-none items-center gap-density-xs marker:hidden">
          <ChevronRight
            aria-hidden
            className="size-3 shrink-0 transition-transform group-open/thinking:rotate-90"
          />
          <ClipboardList aria-hidden className="size-3.5 shrink-0" />
          <span>Earlier thinking</span>
        </summary>
        <div
          className="mt-density-xs space-y-density-xs border-l border-base pl-density-md text-secondary"
          data-testid="claude-code-collapsed-thinking-content"
        >
          {paragraphs.map((paragraph, index) => (
            <p key={`${paragraph.slice(0, 24)}-${index}`} className="whitespace-pre-wrap">
              {paragraph}
            </p>
          ))}
        </div>
      </details>
    </Text>
  );
};

interface FileChangeToolCallCardProps {
  readonly isRunning?: boolean;
  readonly summary: {
    readonly action: 'Edited' | 'Wrote';
    readonly additions: number;
    readonly deletions: number;
    readonly path: string;
    readonly reviewContent: string;
  };
}

const FileChangeToolCallCard = ({ isRunning = false, summary }: FileChangeToolCallCardProps) => {
  const Icon = summary.action === 'Wrote' ? FilePlus2 : FilePenLine;

  return (
    <div
      className="my-density-xs overflow-hidden rounded border border-base bg-surface-raised"
      data-testid="claude-code-tool-call-file-change"
    >
      <details className="group/write" data-testid="claude-code-tool-call-file-change-details">
        <summary className="flex cursor-pointer list-none items-center gap-density-sm px-density-sm py-density-xs marker:hidden">
          <div className="flex size-8 shrink-0 items-center justify-center rounded bg-surface-sunken text-secondary">
            <Icon size={16} />
          </div>
          <div className="min-w-0 flex-1">
            <Text
              kind="label/bold/md"
              className={cn('block', isRunning && RUNNING_TOOL_CALL_CLASS)}
            >
              {summary.action} 1 file
            </Text>
            <Text kind="body/regular/sm" className="block tabular-nums">
              <span className={FILE_CHANGE_ADDITION_CLASS}>+{summary.additions}</span>{' '}
              <span className={FILE_CHANGE_DELETION_CLASS}>-{summary.deletions}</span>
            </Text>
          </div>
          <span className="flex shrink-0 items-center gap-density-xs rounded border border-base px-density-sm py-density-xs text-secondary group-open/write:bg-surface-sunken">
            <Text kind="label/regular/sm">Review</Text>
            <ChevronRight size={14} className="transition-transform group-open/write:rotate-90" />
          </span>
        </summary>
        <div className="border-t border-base px-density-sm py-density-xs">
          <pre
            className={`max-h-72 overflow-auto rounded ${CODE_BLOCK_SURFACE_CLASS} p-density-sm text-xs leading-relaxed text-secondary`}
            data-testid="claude-code-tool-call-file-change-review-surface"
          >
            <code data-testid="claude-code-tool-call-file-change-review">
              {summary.reviewContent}
            </code>
          </pre>
        </div>
      </details>
      <div className="border-t border-base px-density-sm py-density-xs">
        <div className="flex min-w-0 items-center justify-between gap-density-md">
          <Text kind="body/regular/sm" className="min-w-0 truncate">
            {summary.path}
          </Text>
          <Text kind="body/regular/sm" className="shrink-0 tabular-nums">
            <span className={FILE_CHANGE_ADDITION_CLASS}>+{summary.additions}</span>{' '}
            <span className={FILE_CHANGE_DELETION_CLASS}>-{summary.deletions}</span>
          </Text>
        </div>
      </div>
    </div>
  );
};

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
