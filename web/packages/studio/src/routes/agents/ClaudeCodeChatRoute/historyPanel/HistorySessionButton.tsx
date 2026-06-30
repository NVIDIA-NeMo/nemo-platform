// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { ToolCallSummary } from '@studio/routes/agents/ClaudeCodeChatRoute/historyPanel/ArtifactSections';
import {
  getCompactRelativeTime,
  getHistorySessionTitle,
} from '@studio/routes/agents/ClaudeCodeChatRoute/historyPanel/helpers';
import type { ClaudeCodeHistorySession } from '@studio/routes/agents/ClaudeCodeChatRoute/types';
import cn from 'classnames';
import { MessageSquare } from 'lucide-react';

export const HistorySessionButton = ({
  active,
  onSelect,
  session,
}: {
  active: boolean;
  onSelect: () => void;
  session: ClaudeCodeHistorySession;
}) => {
  const sessionTitle = getHistorySessionTitle(session);
  const timestamp = new Date(session.mtime * 1000).toLocaleString();
  const prompt = session.first_prompt.trim();
  const tooltip = prompt ? `${timestamp}\n\n${prompt}` : timestamp;

  return (
    <button
      type="button"
      aria-current={active ? 'page' : undefined}
      title={tooltip}
      className={cn(
        'w-full cursor-pointer border-b border-base px-density-md py-density-sm text-left transition-colors hover:bg-surface-sunken focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent',
        active && 'bg-surface-sunken'
      )}
      onClick={onSelect}
    >
      <Stack gap="density-xs">
        <Flex align="center" gap="density-sm">
          <span
            className={cn(
              'flex size-6 shrink-0 items-center justify-center text-secondary',
              active && 'text-accent'
            )}
          >
            <MessageSquare size={12} />
          </span>
          <Flex align="center" justify="between" gap="density-sm" className="min-w-0 flex-1">
            <Text kind="body/regular/sm" className="min-w-0 flex-1 line-clamp-2">
              {sessionTitle}
            </Text>
            <Text kind="body/regular/sm" color="secondary" className="shrink-0 whitespace-nowrap">
              {getCompactRelativeTime(session.mtime)}
            </Text>
          </Flex>
        </Flex>
        {session.tool_calls.length > 0 && (
          <div className="pl-8">
            <ToolCallSummary toolCalls={session.tool_calls} />
          </div>
        )}
      </Stack>
    </button>
  );
};
