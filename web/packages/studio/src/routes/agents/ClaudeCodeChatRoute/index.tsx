// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AssistantRuntimeProvider } from '@assistant-ui/react';
import { AssistantChatThread } from '@nemo/common/src/components/AssistantChat/AssistantChatThread';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { Stack } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import type { ClaudeCodeChatRouteState } from '@studio/routes/agents/ClaudeCodeChatRoute/types';
import { useClaudeCodeChatRuntime } from '@studio/routes/agents/ClaudeCodeChatRoute/useClaudeCodeChatRuntime';
import { getWorkspaceDashboardRoute } from '@studio/routes/utils';
import { type FC, useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

const getInitialPrompt = (state: unknown): string | undefined => {
  if (typeof state !== 'object' || state === null) return undefined;

  const initialPrompt = (state as ClaudeCodeChatRouteState).initialPrompt;
  if (typeof initialPrompt !== 'string') return undefined;

  const trimmedPrompt = initialPrompt.trim();
  return trimmedPrompt || undefined;
};

export const ClaudeCodeChatRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const location = useLocation();
  const navigate = useNavigate();
  const toast = useToast();
  const consumedInitialPromptRef = useRef<string | undefined>(undefined);
  const { handleReset, runtime, submitPrompt } = useClaudeCodeChatRuntime({
    onError: (error) => toast.error(error.message),
  });
  const initialPrompt = getInitialPrompt(location.state);

  useBreadcrumbs({
    items: [
      { slotLabel: 'Dashboard', href: getWorkspaceDashboardRoute(workspace) },
      { slotLabel: 'Code Agent' },
    ],
  });

  useEffect(() => {
    if (!initialPrompt || consumedInitialPromptRef.current === initialPrompt) return;

    consumedInitialPromptRef.current = initialPrompt;
    navigate(location.pathname, { replace: true, state: null });
    void submitPrompt(initialPrompt);
  }, [initialPrompt, location.pathname, navigate, submitPrompt]);

  return (
    <AccessibleTitle title={`Code Agent chat for ${workspace}`}>
      <Stack className="h-full" padding="density-2xl">
        <Stack className="mx-auto min-h-0 w-full max-w-180 flex-1">
          <AssistantRuntimeProvider runtime={runtime}>
            <AssistantChatThread
              placeholder="Ask Claude Code to work in this workspace"
              onReset={handleReset}
              emptyState={{
                slotHeading: 'Start a Claude Code session',
                slotSubheading: 'Ask Claude Code to work in this workspace.',
              }}
            />
          </AssistantRuntimeProvider>
        </Stack>
      </Stack>
    </AccessibleTitle>
  );
};
