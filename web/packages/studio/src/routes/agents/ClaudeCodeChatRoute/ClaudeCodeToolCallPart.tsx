// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ToolCallMessagePartComponent } from '@assistant-ui/react';
import { Text } from '@nvidia/foundations-react-core';
import type { ClaudeCodeToolArgs } from '@studio/routes/agents/ClaudeCodeChatRoute/toolParts';
import {
  CheckSquare,
  ChevronRight,
  FilePenLine,
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

const getStringArg = (args: ClaudeCodeToolArgs, keys: string[]): string | undefined => {
  for (const key of keys) {
    const value = args[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
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

const getSubtleToolMessage = (
  toolName: string,
  args: ClaudeCodeToolArgs
): string | undefined => {
  if (toolName === 'Read') {
    const path = getStringArg(args, ['file_path', 'path']);
    return path ? `Read ${getFileName(path)}` : 'Read file';
  }

  return undefined;
};

const formatArgs = (args: ClaudeCodeToolArgs, argsText: string): string => {
  const trimmedArgsText = argsText.trim();
  if (trimmedArgsText && trimmedArgsText !== '{}') return trimmedArgsText;
  return JSON.stringify(args, null, 2);
};

export const ClaudeCodeToolCallPart: ToolCallMessagePartComponent<ClaudeCodeToolArgs, unknown> = ({
  args,
  argsText,
  toolName,
}) => {
  if (toolName === 'Bash') return null;

  const subtleMessage = getSubtleToolMessage(toolName, args);
  if (subtleMessage) {
    return (
      <Text asChild kind="body/regular/sm" color="secondary">
        <div
          className="my-density-xs block w-full text-secondary"
          data-testid="claude-code-tool-call-subtle"
        >
          {subtleMessage}
        </div>
      </Text>
    );
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
        <pre className="mt-density-xs max-h-72 overflow-auto rounded bg-surface-sunken p-density-sm text-xs leading-relaxed text-secondary">
          <code>{formattedArgs}</code>
        </pre>
      </div>
    </details>
  );
};
