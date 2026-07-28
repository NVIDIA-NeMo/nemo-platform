/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

/** Workspace role binding names accepted by the Entities members API (see platform role bindings). */
export const WORKSPACE_MEMBER_ROLES = ['Viewer', 'Editor', 'Exporter', 'Admin'] as const;

export type WorkspaceMemberRole = (typeof WORKSPACE_MEMBER_ROLES)[number];

/** Short descriptions for role selection (Members & access UI). */
export const WORKSPACE_ROLE_DESCRIPTIONS: Record<WorkspaceMemberRole, string> = {
  Viewer: 'View all resources.',
  Editor: 'Create, modify, and delete resources.',
  Exporter: 'View resources and reference them from other workspaces.',
  Admin: 'Full administrative access over resources, users, and access.',
};

/** When editing a member with multiple bindings, pick one role for the radio UI (API order). */
export function primaryWorkspaceMemberRole(roles: string[] | undefined): WorkspaceMemberRole {
  if (!roles?.length) {
    return 'Viewer';
  }
  for (const role of WORKSPACE_MEMBER_ROLES) {
    if (roles.includes(role)) {
      return role;
    }
  }
  return 'Viewer';
}
