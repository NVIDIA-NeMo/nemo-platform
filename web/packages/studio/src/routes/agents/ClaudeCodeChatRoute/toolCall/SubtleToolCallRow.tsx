// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Text } from '@nvidia/foundations-react-core';
import { RUNNING_TOOL_CALL_CLASS } from '@studio/routes/agents/ClaudeCodeChatRoute/toolCall/constants';
import { summarizeRepeatedSubtleToolActions } from '@studio/routes/agents/ClaudeCodeChatRoute/toolCall/helpers';
import type { SubtleToolAction } from '@studio/routes/agents/ClaudeCodeChatRoute/toolCall/types';
import cn from 'classnames';
import { ChevronRight } from 'lucide-react';

interface SubtleToolCallRowProps {
  readonly actions: readonly SubtleToolAction[];
  readonly isRunning?: boolean;
}

export const SubtleToolCallRow = ({ actions, isRunning = false }: SubtleToolCallRowProps) => (
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
