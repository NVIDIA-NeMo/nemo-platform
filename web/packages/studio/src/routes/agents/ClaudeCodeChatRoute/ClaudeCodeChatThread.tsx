// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AssistantRuntimeProvider } from '@assistant-ui/react';
import { AssistantChatThread } from '@nemo/common/src/components/AssistantChat/AssistantChatThread';
import { type AgentBlockingInputSubmission } from '@studio/components/agents/AgentBlockingInput';
import { AgentDecisionInput } from '@studio/components/agents/AgentDecisionInput';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { BlockingInputComposer } from '@studio/routes/agents/ClaudeCodeChatRoute/BlockingInputComposer';
import { ClaudeCodeStudioLink } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeStudioLink';
import { ClaudeCodeToolCallPart } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeToolCallPart';
import type { ClaudeCodeChatRuntime } from '@studio/routes/agents/ClaudeCodeChatRoute/useClaudeCodeChatRuntime';
import { type FC, useCallback, useLayoutEffect, useRef } from 'react';

const CHAT_VIEWPORT_SCROLLBAR_CLASS = [
  '[scrollbar-width:thin]',
  '[scrollbar-color:var(--border-color-interaction-base)_transparent]',
  '[&::-webkit-scrollbar]:w-2',
  '[&::-webkit-scrollbar-corner]:bg-transparent',
  '[&::-webkit-scrollbar-track]:bg-transparent',
  '[&::-webkit-scrollbar-thumb]:rounded-full',
  '[&::-webkit-scrollbar-thumb]:bg-[var(--border-color-interaction-base)]',
  '[&::-webkit-scrollbar-thumb:hover]:bg-[var(--border-color-interaction-strong)]',
].join(' ');

interface ClaudeCodeChatThreadProps {
  chat: ClaudeCodeChatRuntime;
  mode?: 'full' | 'compact';
  onReset?: () => void;
  scrollToBottomSignal?: number;
}

export const ClaudeCodeChatThread: FC<ClaudeCodeChatThreadProps> = ({
  chat,
  mode = 'full',
  onReset,
  scrollToBottomSignal,
}) => {
  const workspace = useWorkspaceFromPath();
  const chatViewportRef = useRef<HTMLDivElement>(null);
  const {
    decisionChoices,
    decisionRequest,
    decisionStatus,
    handleReset,
    inputRequest,
    inputStatus,
    resolveInputRequest,
    resolveDecisionRequest,
    runtime,
    skipInputRequest,
    skipDecisionRequest,
  } = chat;

  const scrollViewportToBottom = useCallback(() => {
    const viewport = chatViewportRef.current;
    if (!viewport) return undefined;

    let secondFrame = 0;
    const firstFrame = window.requestAnimationFrame(() => {
      viewport.scrollTop = viewport.scrollHeight;
      secondFrame = window.requestAnimationFrame(() => {
        viewport.scrollTop = viewport.scrollHeight;
      });
    });

    return () => {
      window.cancelAnimationFrame(firstFrame);
      if (secondFrame) window.cancelAnimationFrame(secondFrame);
    };
  }, []);

  const handleChatReset = useCallback(() => {
    handleReset();
    onReset?.();
  }, [handleReset, onReset]);

  const handleInputSubmit = useCallback(
    async (submission: AgentBlockingInputSubmission) => {
      await resolveInputRequest({
        decision: { value: submission.value },
        displayText: submission.displayText,
      });
    },
    [resolveInputRequest]
  );

  useLayoutEffect(() => {
    if (!decisionRequest && !inputRequest) return undefined;
    return scrollViewportToBottom();
  }, [decisionRequest, inputRequest, scrollViewportToBottom]);

  useLayoutEffect(() => {
    if (scrollToBottomSignal === undefined) return undefined;
    return scrollViewportToBottom();
  }, [scrollToBottomSignal, scrollViewportToBottom]);

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <AssistantChatThread
        contentClassName={
          mode === 'compact' ? 'w-full px-density-lg' : 'mx-auto w-full max-w-180 px-density-2xl'
        }
        composerContainerClassName={
          mode === 'compact' ? 'w-full px-density-lg' : 'mx-auto w-full max-w-180 px-density-2xl'
        }
        viewportClassName={CHAT_VIEWPORT_SCROLLBAR_CLASS}
        hideAssistantMessageActions
        toolCallPartComponent={ClaudeCodeToolCallPart}
        attributes={{
          ThreadViewport: {
            ref: chatViewportRef,
          },
        }}
        placeholder="Ask Claude Code to work in this workspace"
        onReset={handleChatReset}
        showRunningIndicator={!decisionRequest && !inputRequest}
        messageContentProps={{ markdownLinkComponent: ClaudeCodeStudioLink }}
        emptyState={{
          slotHeading: 'Start a Claude Code session',
          slotSubheading: 'Ask Claude Code to work in this workspace.',
        }}
        composerOverride={
          decisionRequest ? (
            <AgentDecisionInput
              request={decisionRequest}
              choices={decisionChoices}
              defaultChoiceId={decisionChoices[0]?.id}
              status={decisionStatus}
              onSubmit={resolveDecisionRequest}
              onSkip={skipDecisionRequest}
            />
          ) : inputRequest ? (
            <BlockingInputComposer
              inputRequest={inputRequest}
              inputStatus={inputStatus}
              workspace={workspace}
              onSubmit={handleInputSubmit}
              onSkip={skipInputRequest}
            />
          ) : undefined
        }
      />
    </AssistantRuntimeProvider>
  );
};
