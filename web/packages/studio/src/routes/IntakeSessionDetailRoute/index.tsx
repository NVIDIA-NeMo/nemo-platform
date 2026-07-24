// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  type SessionDetailRouteContext,
  SessionDetailView,
} from '@studio/components/IntakeDetail/SessionDetailView';
import { NotFound } from '@studio/components/Layouts/NotFound';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import type { FC } from 'react';
import { useParams } from 'react-router-dom';

interface SessionDetailContentProps {
  sessionId: string;
  routeContext?: SessionDetailRouteContext;
}

export const SessionDetailContent: FC<SessionDetailContentProps> = (props) => {
  const workspace = useWorkspaceFromPath();
  return <SessionDetailView workspace={workspace} {...props} />;
};

type SessionRouteParams = Record<typeof ROUTE_PARAMS.sessionId, string | undefined>;

export const IntakeSessionDetailRoute: FC = () => {
  const { [ROUTE_PARAMS.sessionId]: sessionId } = useParams<SessionRouteParams>();
  if (!sessionId) {
    return (
      <NotFound
        subheader="Session Not Found"
        message="The session route is missing a session ID."
      />
    );
  }
  return <SessionDetailContent sessionId={sessionId} />;
};
