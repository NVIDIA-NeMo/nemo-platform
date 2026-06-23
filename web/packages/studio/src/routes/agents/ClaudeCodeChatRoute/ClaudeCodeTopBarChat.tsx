// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Button, Flex, Popover, Stack, Tooltip } from '@nvidia/foundations-react-core';
import { CODING_AGENT_STUDIO_ENABLED } from '@studio/constants/environment';
import { useWorkspaceFromPathIfExists } from '@studio/hooks/useWorkspaceFromPath';
import { ClaudeCodeChatThread } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeChatThread';
import { useClaudeCodeChatContext } from '@studio/routes/agents/ClaudeCodeChatRoute/context/useClaudeCodeChatContext';
import { getClaudeCodeChatRouteForSession } from '@studio/routes/agents/ClaudeCodeChatRoute/util';
import { getClaudeCodeChatRoute } from '@studio/routes/utils';
import { Maximize2, Plus, Terminal, X } from 'lucide-react';
import { type FC, type MouseEvent, useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';

const OPEN_LABEL = 'Open Code Agent chat';
const CLOSE_LABEL = 'Close Code Agent chat';

const TopBarChatIcon = () => <Terminal size={16} />;

/**
 * The top-bar pop-out is a thin view of the shared chat runtime (owned by
 * ClaudeCodeChatProvider). Because the runtime lives above the routes, opening
 * the pop-out mid-run shows the live stream and thinking/awaiting-input state.
 */
const ClaudeCodeTopBarChatPopout: FC<{ workspace: string }> = ({ workspace }) => {
  const navigate = useNavigate();
  const { chat, startNewChat } = useClaudeCodeChatContext();
  const { decisionRequest, inputRequest, isRunning, sessionId } = chat;
  const [isOpen, setIsOpen] = useState(false);
  const [hasUnreadResponse, setHasUnreadResponse] = useState(false);
  const [scrollToBottomSignal, setScrollToBottomSignal] = useState(0);

  // While the agent is blocked on a permission/input request the stream stays
  // open (isRunning is still true), but it is waiting on the user rather than
  // thinking — surface the attention badge instead of the loading dots.
  const isAwaitingUserInput = !!decisionRequest || !!inputRequest;

  // Surface an unread badge when the agent finishes responding while the
  // pop-out is closed, and clear it the moment the user opens the chat.
  const wasRunningRef = useRef(false);
  useEffect(() => {
    if (isOpen) {
      setHasUnreadResponse(false);
    } else if (wasRunningRef.current && !isRunning) {
      setHasUnreadResponse(true);
    }
    wasRunningRef.current = isRunning;
  }, [isOpen, isRunning]);

  // The popover dismisses on Esc / outside click; just mirror that here.
  const handleOpenChange = useCallback((open: boolean) => {
    if (!open) setIsOpen(false);
  }, []);

  // The controlled popover treats this trigger as "outside" its content, so a
  // pointer-down would dismiss it right before the click re-opens it. Stop that
  // dismissal while open and let the click own the toggle.
  const handleTriggerPointerDown = useCallback(
    (event: MouseEvent<HTMLButtonElement>) => {
      if (isOpen) event.stopPropagation();
    },
    [isOpen]
  );

  const handleTriggerClick = useCallback(
    (event: MouseEvent<HTMLButtonElement>) => {
      event.preventDefault();
      if (isOpen) {
        setIsOpen(false);
        return;
      }
      setIsOpen(true);
      setScrollToBottomSignal((signal) => signal + 1);
    },
    [isOpen]
  );

  // Close the pop-out when the user follows an in-chat link to another route.
  // This runs on the bubble phase (not capture) so the link's own react-router
  // navigation happens first — closing the popover out from under the anchor
  // mid-click breaks client-side navigation and triggers a full reload.
  const handlePopoverLinkClick = useCallback((event: MouseEvent<HTMLElement>) => {
    if (event.target instanceof Element && event.target.closest('a[href]')) {
      setIsOpen(false);
    }
  }, []);

  // The full chat route shares this runtime, so it opens on the same live
  // session (continuing any in-flight run).
  const handleOpenFullChat = useCallback(() => {
    setIsOpen(false);
    navigate(
      sessionId
        ? getClaudeCodeChatRouteForSession(workspace, sessionId)
        : getClaudeCodeChatRoute(workspace)
    );
  }, [navigate, sessionId, workspace]);

  return (
    <>
      {isOpen &&
        typeof document !== 'undefined' &&
        createPortal(
          <div
            data-testid="code-agent-chat-backdrop"
            aria-hidden="true"
            className="fixed inset-0 z-[1000] bg-black/40 backdrop-blur-[1px]"
            onClick={() => setIsOpen(false)}
          />,
          document.body
        )}
      <Popover
        align="end"
        open={isOpen}
        side="bottom"
        className="z-[1001] !max-h-[calc(100vh-var(--nv-app-bar-height)-48px)] max-w-[calc(100vw-48px)] !overflow-hidden !rounded-xl !bg-surface-sunken !p-0 translate-y-1 dark:!bg-surface-raised"
        onOpenChange={handleOpenChange}
        slotContent={
          <Stack
            className="min-h-0 h-[min(820px,calc(100vh-var(--nv-app-bar-height)-48px))] w-[min(920px,calc(100vw-192px))] overflow-hidden bg-surface-sunken p-density-md text-primary dark:bg-surface-raised"
            gap="density-md"
            onClick={handlePopoverLinkClick}
          >
            <Flex align="center" justify="between" gap="density-md">
              <Button kind="tertiary" size="small" onClick={startNewChat}>
                <Plus size={14} />
                New
              </Button>
              <Flex align="center" gap="density-xs">
                <Tooltip slotContent="Open in main chat" side="bottom">
                  <Button
                    kind="tertiary"
                    size="small"
                    aria-label="Open in main chat"
                    onClick={handleOpenFullChat}
                  >
                    <Maximize2 size={16} />
                  </Button>
                </Tooltip>
                <Button
                  kind="tertiary"
                  size="small"
                  aria-label="Close chat window"
                  onClick={() => setIsOpen(false)}
                >
                  <X size={16} />
                </Button>
              </Flex>
            </Flex>
            <Stack className="min-h-0 flex-1 overflow-hidden">
              <ClaudeCodeChatThread
                chat={chat}
                mode="compact"
                scrollToBottomSignal={scrollToBottomSignal}
              />
            </Stack>
          </Stack>
        }
      >
        <Button
          kind="tertiary"
          size="small"
          aria-label={isOpen ? CLOSE_LABEL : OPEN_LABEL}
          className="relative"
          title={isOpen ? CLOSE_LABEL : OPEN_LABEL}
          onPointerDown={handleTriggerPointerDown}
          onClick={handleTriggerClick}
        >
          <TopBarChatIcon />
          {isRunning && !isAwaitingUserInput ? (
            <span
              className="pointer-events-none absolute right-0 top-0 flex h-3 w-5 items-center justify-center gap-0.5 rounded-full border border-base bg-surface-sunken/90 dark:bg-surface-raised/90"
              data-testid="code-agent-thinking-indicator"
            >
              <span
                className="size-1 animate-pulse rounded-full bg-brand"
                data-testid="code-agent-thinking-dot"
              />
              <span
                className="size-1 animate-pulse rounded-full bg-brand [animation-delay:150ms]"
                data-testid="code-agent-thinking-dot"
              />
              <span
                className="size-1 animate-pulse rounded-full bg-brand [animation-delay:300ms]"
                data-testid="code-agent-thinking-dot"
              />
            </span>
          ) : isAwaitingUserInput || hasUnreadResponse ? (
            <span
              className="pointer-events-none absolute right-1 top-1 size-2 rounded-full bg-brand ring-2 ring-surface-sunken dark:ring-surface-raised"
              data-testid="code-agent-unread-indicator"
            />
          ) : null}
        </Button>
      </Popover>
    </>
  );
};

export const ClaudeCodeTopBarChat: FC = () => {
  const workspace = useWorkspaceFromPathIfExists();

  if (!CODING_AGENT_STUDIO_ENABLED || !workspace) return null;

  return <ClaudeCodeTopBarChatPopout workspace={workspace} />;
};
