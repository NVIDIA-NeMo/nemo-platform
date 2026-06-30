// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AppBar, Button, Flex, Stack, Text, Tooltip } from '@nvidia/foundations-react-core';
import { Breadcrumbs } from '@studio/components/Breadcrumbs';
import { UserPopover } from '@studio/components/UserPopover';
import { TOUR_ENABLED } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { useWorkspaceFromPathIfExists } from '@studio/hooks/useWorkspaceFromPath';
import { ClaudeCodeTopBarChat } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeTopBarChat';
import { ThemeSwitch } from '@studio/routes/PageLayout/ThemeSwitch';
import { getWorkspaceDetailsDefaultRoute } from '@studio/routes/utils';
import { useSidebarState } from '@studio/util/hooks/useSidebarState';
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { lazy, Suspense, type FC, type ReactNode } from 'react';
import { Link, matchPath, useLocation } from 'react-router-dom';

const WelcomeTour = lazy(() =>
  import('@studio/components/WelcomeTour').then((m) => ({ default: m.WelcomeTour }))
);

interface Props {
  sideNav?: (collapsed: boolean) => ReactNode;
}

export const GlobalNav: FC<Props> = ({ sideNav }) => {
  const { expanded, toggle } = useSidebarState();
  const workspace = useWorkspaceFromPathIfExists();
  const location = useLocation();
  const isDashboardRoute =
    matchPath({ path: ROUTES.workspace.dashboard, end: true }, location.pathname) !== null;
  const isClaudeCodeChatRoute =
    matchPath({ path: ROUTES.workspace.claudeCodeChat, end: true }, location.pathname) !== null;
  const shouldMountClaudeCodeTopBarChat = !isDashboardRoute && !isClaudeCodeChatRoute;

  const toggleLabel = expanded ? 'Collapse sidebar' : 'Expand sidebar';
  const ToggleSidebarButton = (
    <Tooltip slotContent={toggleLabel} side="right">
      <Button
        kind="tertiary"
        size="small"
        aria-label={toggleLabel}
        onClick={toggle}
        disabled={!sideNav}
      >
        {expanded ? <PanelLeftClose /> : <PanelLeftOpen />}
      </Button>
    </Tooltip>
  );

  return (
    <>
      <Flex
        className={`[grid-area:logobar] bg-surface-navigation transition-colors border-r border-b border-base ${expanded ? 'pl-4 pr-2' : ''}`}
        align="center"
        gap="density-md"
        justify={expanded ? 'between' : 'center'}
      >
        {expanded && (
          <Stack direction="row" align="center" gap="density-sm" asChild>
            <Link to={workspace ? getWorkspaceDetailsDefaultRoute(workspace) : '/'}>
              <Text kind="label/bold/md">NeMo Studio</Text>
            </Link>
          </Stack>
        )}
        {ToggleSidebarButton}
      </Flex>
      <AppBar
        className="[grid-area:navbar] transition-colors"
        slotStart={
          <Flex gap="density-md" align="center" data-tour="nav-workspace">
            <Breadcrumbs />
          </Flex>
        }
        slotEnd={
          <Flex gap="density-md" align="center">
            {TOUR_ENABLED && (
              <Suspense>
                <WelcomeTour />
              </Suspense>
            )}
            {shouldMountClaudeCodeTopBarChat && <ClaudeCodeTopBarChat />}
            <ThemeSwitch />
            <span data-tour="nav-user">
              <UserPopover />
            </span>
          </Flex>
        }
      />
      {sideNav && (
        <div
          className="h-full max-h-[calc(100vh-var(--nv-app-bar-height))] overflow-y-auto [grid-area:sidebar]"
          data-tour="sidebar"
        >
          {sideNav(!expanded)}
        </div>
      )}
    </>
  );
};
