// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { COPILOT_ACTIVE_SESSION_KEY_PREFIX } from '@studio/util/localStorage';

export const getCopilotActiveSessionStorageKey = (workspace: string): string =>
  `${COPILOT_ACTIVE_SESSION_KEY_PREFIX}:${workspace}`;

export const readStoredActiveSessionId = (workspace: string | undefined): string | undefined => {
  if (!workspace || typeof window === 'undefined') return undefined;

  try {
    const storedSessionId = window.localStorage
      .getItem(getCopilotActiveSessionStorageKey(workspace))
      ?.trim();
    return storedSessionId || undefined;
  } catch {
    return undefined;
  }
};

export const writeStoredActiveSessionId = (
  workspace: string | undefined,
  sessionId: string | null
): void => {
  if (!workspace || typeof window === 'undefined') return;

  try {
    const storageKey = getCopilotActiveSessionStorageKey(workspace);
    if (sessionId) {
      window.localStorage.setItem(storageKey, sessionId);
    } else {
      window.localStorage.removeItem(storageKey);
    }
  } catch {
    // localStorage can be unavailable in restricted browser modes.
  }
};
