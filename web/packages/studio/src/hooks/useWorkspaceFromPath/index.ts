// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { useParams } from 'react-router-dom';

/**
 * Returns the workspace
 * /workspace/my-workspace -> my-workspace
 */
export function useWorkspaceFromPath(): string {
  const { workspace } = useRequiredPathParams([ROUTE_PARAMS.workspace]);

  return workspace;
}

/**
 * Returns the workspace name from the path IF there is a workspace in the path,
 * use `useWorkspaceFromPath` if you want to guarantee that there is a workspace in the path.
 */
export const useWorkspaceFromPathIfExists = () => {
  const workspace = useParams()[ROUTE_PARAMS.workspace];

  return workspace || undefined;
};

/**
 * Returns the workspace name from the path or the prop workspace if provided.
 * use `useWorkspaceFromPath` if you want to guarantee that there is a workspace in the path.
 */
export const useWorkspaceFromPathOrProp = (propWorkspace?: string) => {
  const pathWs = useWorkspaceFromPath();
  return propWorkspace ?? pathWs;
};
