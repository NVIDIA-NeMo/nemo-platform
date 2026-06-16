// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useLocalStorage } from '@studio/util/hooks/useLocalStorage';
import { useCallback, useMemo } from 'react';

/** localStorage key prefix for pinned experiment ids, scoped per workspace + group below. */
const PINNED_STORAGE_PREFIX = 'nemo:experiments:pinned';

export interface PinnedExperiments {
  /** Set of pinned experiment ids for O(1) membership checks. */
  pinnedSet: Set<string>;
  /** Pins the experiment if unpinned, unpins it otherwise. */
  togglePin: (id: string) => void;
}

/**
 * Tracks which experiments the user has pinned to the top of the list, persisted in the browser's
 * localStorage. Pins are scoped per workspace + experiment group so each group keeps its own set.
 *
 * `groupName` is used (rather than the group id) because it is available synchronously from the
 * route, avoiding a key change while the group id loads asynchronously.
 */
export function usePinnedExperiments(workspace: string, groupName: string): PinnedExperiments {
  const [pinnedIds = [], setPinnedIds] = useLocalStorage<string[]>(
    `${PINNED_STORAGE_PREFIX}:${workspace}:${groupName}`,
    []
  );

  const pinnedSet = useMemo(() => new Set(pinnedIds), [pinnedIds]);

  const togglePin = useCallback(
    (id: string) => {
      setPinnedIds(pinnedSet.has(id) ? pinnedIds.filter((p) => p !== id) : [...pinnedIds, id]);
    },
    [pinnedIds, pinnedSet, setPinnedIds]
  );

  return { pinnedSet, togglePin };
}
