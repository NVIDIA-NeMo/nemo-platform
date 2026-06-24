// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { GlobalNav } from '@studio/components/Layouts/GlobalNav';
import { CODING_AGENT_STUDIO_ENABLED } from '@studio/constants/environment';
import { useWorkspaceFromPathIfExists } from '@studio/hooks/useWorkspaceFromPath';
import { useAuthAutoLogin } from '@studio/providers/auth';
import { useAuthTokenStatus } from '@studio/providers/auth/useAuthTokenStatus';
import { useSelectedWorkspace } from '@studio/providers/workspace';
import { ClaudeCodeChatProvider } from '@studio/routes/agents/ClaudeCodeChatRoute/context/ClaudeCodeChatProvider';
import { WorkspaceGuard } from '@studio/routes/RootLayout/WorkspaceGuard';
import { ReactNode } from 'react';
import { Outlet } from 'react-router-dom';

export const PageLayout = ({ sideNav }: { sideNav?: (collapsed: boolean) => ReactNode }) => {
  const { isAuthPending } = useAuthAutoLogin();
  const { isTokenActive } = useAuthTokenStatus();
  const { selectedWorkspace, isWorkspaceUnauthorized, isWorkspaceLoading } = useSelectedWorkspace();
  const workspace = useWorkspaceFromPathIfExists();

  if (isAuthPending) {
    return null;
  }

  const workspaceCheckActive = isTokenActive && !!selectedWorkspace;
  const hideSideNav = workspaceCheckActive && (isWorkspaceLoading || isWorkspaceUnauthorized);

  const gridAreas = hideSideNav
    ? "[grid-template-areas:'logobar_navbar''content_content']"
    : "[grid-template-areas:'logobar_navbar''sidebar_content']";

  // Rendered as direct grid children; the provider adds no DOM of its own, so
  // it can wrap both the nav (pop-out chat) and the outlet (full chat) while
  // keeping a single shared chat runtime alive across workspace navigation.
  const layout = (
    <>
      <GlobalNav sideNav={hideSideNav ? undefined : sideNav} />
      <div className="bg-surface-sunken transition-colors relative h-full max-h-[calc(100vh-var(--nv-app-bar-height))] overflow-y-auto [grid-area:content]">
        <WorkspaceGuard>
          <Outlet />
        </WorkspaceGuard>
      </div>
    </>
  );

  return (
    <div
      className={`min-h-screen relative grid size-full text-primary grid-cols-[auto_minmax(0,1fr)] grid-rows-[auto_1fr] ${gridAreas}`}
    >
      {CODING_AGENT_STUDIO_ENABLED && workspace ? (
        <ClaudeCodeChatProvider key={workspace} workspace={workspace}>
          {layout}
        </ClaudeCodeChatProvider>
      ) : (
        layout
      )}
    </div>
  );
};
