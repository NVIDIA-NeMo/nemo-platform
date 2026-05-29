// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getModelCompareRoute } from '@studio/routes/utils';
import type { FC } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

/**
 * Permanent redirect from the legacy `/workspaces/:workspace/playground` URL
 * to the consolidated Chat route. Preserves the query string (?agent=, ...).
 */
export const PlaygroundRedirect: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { search } = useLocation();
  return <Navigate to={getModelCompareRoute(workspace) + search} replace />;
};
