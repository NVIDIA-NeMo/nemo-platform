// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ToolCallMessagePartComponent } from '@assistant-ui/react';
import { Text } from '@nvidia/foundations-react-core';
import {
  isClaudeCodeToolCallOmitted,
  type ClaudeCodeToolArgs,
} from '@studio/routes/agents/ClaudeCodeChatRoute/toolParts';
import {
  CheckSquare,
  ChevronRight,
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
  if (toolName === 'Read') {
    const path = getStringArg(args, ['file_path', 'path']);
    return path ? `Read ${getFileName(path)}` : 'Read file';
  }

  return undefined;
};

interface FileChangeToolCallCardProps {
  readonly summary: {
    readonly action: 'Edited' | 'Wrote';
    readonly additions: number;
    readonly deletions: number;
    readonly path: string;
    readonly reviewContent: string;
  };
}

const FileChangeToolCallCard = ({ summary }: FileChangeToolCallCardProps) => {
  const Icon = summary.action === 'Wrote' ? FilePlus2 : FilePenLine;

  return (
    <div
      className="my-density-sm overflow-hidden rounded border border-base bg-surface-raised"
      data-testid="claude-code-tool-call-file-change"
    >
      <details className="group/write" data-testid="claude-code-tool-call-file-change-details">
        <summary className="flex cursor-pointer list-none items-center gap-density-sm px-density-md py-density-sm marker:hidden">
          <div className="flex size-9 shrink-0 items-center justify-center rounded bg-surface-sunken text-secondary">
            <Icon size={18} />
          </div>
          <div className="min-w-0 flex-1">
            <Text kind="label/bold/md" className="block">
              {summary.action} 1 file
            </Text>
            <Text kind="body/regular/sm" className="block tabular-nums">
              <span className="text-success">+{summary.additions}</span>{' '}
              <span className="text-danger">-{summary.deletions}</span>
            </Text>
          </div>
          <span className="flex shrink-0 items-center gap-density-xs rounded border border-base px-density-sm py-density-xs text-secondary group-open/write:bg-surface-sunken">
            <Text kind="label/regular/sm">Review</Text>
            <ChevronRight size={14} className="transition-transform group-open/write:rotate-90" />
          </span>
        </summary>
        <div className="border-t border-base px-density-md py-density-sm">
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
      <div className="border-t border-base px-density-md py-density-sm">
        <div className="flex min-w-0 items-center justify-between gap-density-md">
          <Text kind="body/regular/sm" className="min-w-0 truncate">
            {summary.path}
          </Text>
          <Text kind="body/regular/sm" className="shrink-0 tabular-nums">
            <span className="text-success">+{summary.additions}</span>{' '}
            <span className="text-danger">-{summary.deletions}</span>
          </Text>
        </div>
      </div>
    </div>
  );
};

export const ClaudeCodeToolCallPart: ToolCallMessagePartComponent<ClaudeCodeToolArgs, unknown> = ({
  args,
  argsText,
  toolName,
}) => {
  if (isClaudeCodeToolCallOmitted(toolName)) return null;

  const subtleMessage = getSubtleToolMessage(toolName, args);
  if (subtleMessage) {
    return (
      <Text asChild kind="body/regular/sm" color="secondary">
        <div
          className="my-0.5 block w-full text-secondary"
          data-testid="claude-code-tool-call-subtle"
        >
          {subtleMessage}
        </div>
      </Text>
    );
  }

  if (toolName === 'Write' || toolName === 'Edit' || toolName === 'MultiEdit') {
    const fileChangeSummary = getFileChangeSummary(toolName, args, argsText);
    if (fileChangeSummary) return <FileChangeToolCallCard summary={fileChangeSummary} />;
  }

  const label = TOOL_LABELS[toolName] ?? toolName;
  const Icon = TOOL_ICONS[toolName] ?? Terminal;
  const summary = getToolSummary(toolName, args);
  const formattedArgs = formatArgs(args, argsText);

  return (
    <details
      className="group/tool my-density-xs rounded border border-base bg-surface-raised"
      data-testid="claude-code-tool-call"
    >
      <summary className="flex cursor-pointer list-none items-center gap-density-xs px-density-sm py-density-xs marker:hidden">
        <ChevronRight
          size={14}
          className="shrink-0 text-secondary transition-transform group-open/tool:rotate-90"
        />
        <Icon size={14} className="shrink-0 text-secondary" />
        <Text kind="label/bold/sm" className="shrink-0">
          {label}
        </Text>
        {summary && (
          <Text kind="body/regular/sm" color="secondary" className="min-w-0 truncate">
            {summary}
          </Text>
        )}
      </summary>
      <div className="border-t border-base px-density-md py-density-sm">
        <Text kind="label/bold/sm" color="secondary">
          Input
        </Text>
        <pre
          className={`mt-density-xs max-h-72 overflow-auto rounded ${CODE_BLOCK_SURFACE_CLASS} p-density-sm text-xs leading-relaxed text-secondary`}
          data-testid="claude-code-tool-call-input-surface"
        >
          <code>{formattedArgs}</code>
        </pre>
      </div>
    </details>
  );
};
