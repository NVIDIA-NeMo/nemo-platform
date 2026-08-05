// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getAgentsListRoute } from '@studio/routes/utils';
import { type FC } from 'react';
import { Navigate } from 'react-router';

/**
 * Agent deployments are now shown on the combined Agents page.
 * This route redirects to maintain backward compatibility with any
 * bookmarked URLs.
 */
export const AgentDeploymentsListRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  return <Navigate to={getAgentsListRoute(workspace)} replace />;
};
