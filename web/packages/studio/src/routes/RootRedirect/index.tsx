// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DEFAULT_WORKSPACE } from '@nemo/common/src/models/constants';
import { useAuthProfile } from '@studio/providers/auth';
import { getWorkspaceDetailsDefaultRoute } from '@studio/routes/utils';
import { useLocalStorage } from '@studio/util/hooks/useLocalStorage';
import { WORKSPACE_DROPDOWN_RECENT_KEY } from '@studio/util/localStorage';
import type { FC } from 'react';
import { Navigate } from 'react-router';

export const RootRedirect: FC = () => {
  const [recentWorkspaces] = useLocalStorage<string[]>(WORKSPACE_DROPDOWN_RECENT_KEY);
  const profile = useAuthProfile();

  const workspace = recentWorkspaces?.[0] || profile?.workspace || DEFAULT_WORKSPACE;

  return <Navigate to={getWorkspaceDetailsDefaultRoute(workspace)} replace />;
};
