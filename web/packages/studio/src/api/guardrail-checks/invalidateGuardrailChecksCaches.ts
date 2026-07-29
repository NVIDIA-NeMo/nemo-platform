// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  getGuardrailCheckQueryKey,
  getGuardrailChecksQueryKey,
} from '@studio/api/guardrail-checks/guardrailChecks';
import { queryClient } from '@studio/api/queryClient';

/**
 * Invalidates guardrail check query caches.
 * Use after mutations that create/update/delete/run checks.
 * Pass `name` to also invalidate a specific check's detail query.
 */
export function invalidateGuardrailChecksCaches(workspace: string, name?: string): Promise<void[]> {
  const ops: Promise<void>[] = [
    queryClient.invalidateQueries({ queryKey: getGuardrailChecksQueryKey(workspace) }),
  ];
  if (name) {
    ops.push(
      queryClient.invalidateQueries({ queryKey: getGuardrailCheckQueryKey(workspace, name) })
    );
  }
  return Promise.all(ops);
}
