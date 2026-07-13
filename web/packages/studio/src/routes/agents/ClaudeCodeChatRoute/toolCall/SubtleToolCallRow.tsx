// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Text } from '@nvidia/foundations-react-core';
import { CODE_BLOCK_SURFACE_CLASS } from '@studio/routes/agents/ClaudeCodeChatRoute/toolCall/constants';
import { summarizeRepeatedSubtleToolActions } from '@studio/routes/agents/ClaudeCodeChatRoute/toolCall/helpers';
import type { SubtleToolAction } from '@studio/routes/agents/ClaudeCodeChatRoute/toolCall/types';
import { ChevronRight, Copy } from 'lucide-react';

interface SubtleToolCallRowProps {
  readonly actions: readonly SubtleToolAction[];
}

interface InvocationPanelProps {
  readonly invocation: string;
  readonly invocationCount: number;
  readonly invocationIndex: number;
  readonly toolCallId: string;
}

const copyInvocation = (invocation: string): void => {
  if (!navigator.clipboard) return;
  void navigator.clipboard.writeText(invocation).catch(() => undefined);
};

const InvocationPanel = ({
  invocation,
  invocationCount,
  invocationIndex,
  toolCallId,
}: InvocationPanelProps) => (
  <div
    className="min-w-0"
    data-testid="claude-code-tool-call-invocation"
    id={`${toolCallId}-invocation-${invocationIndex}`}
  >
    <div className="relative">
      <button
        aria-label={`Copy invocation${invocationCount === 1 ? '' : ` ${invocationIndex + 1}`}`}
        className="absolute right-density-xs top-density-xs z-10 rounded p-0.5 hover:bg-surface-sunken"
        onClick={() => copyInvocation(invocation)}
        title="Copy invocation"
        type="button"
      >
        <Copy aria-hidden className="size-3.5" />
      </button>
      <pre
        className={`max-h-72 overflow-auto whitespace-pre-wrap break-words rounded ${CODE_BLOCK_SURFACE_CLASS} p-density-sm pr-density-xl text-xs leading-relaxed text-secondary`}
      >
        <code data-testid="claude-code-tool-call-invocation-content">{invocation}</code>
      </pre>
    </div>
  </div>
);

export const SubtleToolCallRow = ({ actions }: SubtleToolCallRowProps) => (
  <Text asChild kind="body/regular/sm">
    <div
      className="my-density-xs flex max-w-full flex-wrap items-center gap-x-density-sm gap-y-density-xs rounded border border-base border-l-2 border-l-[var(--border-color-accent-blue)] bg-[color-mix(in_srgb,var(--background-color-accent-blue-subtle)_38%,var(--background-color-surface-base))] px-density-sm py-density-xs text-secondary"
      data-testid="claude-code-tool-call-subtle"
      title={actions.map((action) => action.title ?? action.message).join(' | ')}
    >
      {summarizeRepeatedSubtleToolActions(actions).map((action, index) => {
        const Icon = action.Icon;
        const key = `${action.toolCallId}-${index}`;

        const invocations = action.invocations ?? [action.invocation];

        if (action.details?.length || invocations.length) {
          return (
            <details
              key={key}
              className="group/subtle max-w-full basis-full"
              data-testid="claude-code-tool-call-subtle-details"
            >
              <summary
                className="inline-flex basis-full cursor-pointer list-none items-center gap-density-xs marker:hidden"
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
              {action.details?.length ? (
                <div
                  className="mt-0.5 max-w-full space-y-0.5 pl-7"
                  data-testid="claude-code-tool-call-subtle-detail-list"
                >
                  {action.details.map((detail, detailIndex) => {
                    const invocation = invocations[detailIndex];
                    if (!invocation) return null;

                    return (
                      <details
                        key={`${action.toolCallId}-${detailIndex}`}
                        className="group/invocation min-w-0"
                        data-testid="claude-code-tool-call-nested-invocation"
                      >
                        <summary
                          className="flex cursor-pointer list-none items-center gap-density-xs py-0.5 marker:hidden"
                          data-testid="claude-code-tool-call-subtle-detail-item"
                          title={detail}
                        >
                          <span className="min-w-0 truncate">{detail}</span>
                          <ChevronRight
                            aria-hidden
                            className="size-3 shrink-0 transition-transform group-open/invocation:rotate-90"
                          />
                        </summary>
                        <div className="mt-density-xs pl-density-sm">
                          <InvocationPanel
                            invocation={invocation}
                            invocationCount={invocations.length}
                            invocationIndex={detailIndex}
                            toolCallId={action.toolCallId}
                          />
                        </div>
                      </details>
                    );
                  })}
                </div>
              ) : (
                <div className="mt-density-xs pl-7">
                  <InvocationPanel
                    invocation={invocations[0]!}
                    invocationCount={1}
                    invocationIndex={0}
                    toolCallId={action.toolCallId}
                  />
                </div>
              )}
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
