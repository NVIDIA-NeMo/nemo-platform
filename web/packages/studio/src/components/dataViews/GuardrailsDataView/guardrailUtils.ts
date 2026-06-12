// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfigOutput } from '@nemo/sdk/generated/platform/schema';

/**
 * Count the total number of configured rail flows across input, output, and
 * retrieval rails. Returns 0 if the config or rails are absent.
 *
 * Note: DialogRails does not expose a `flows` field in the SDK schema, so
 * dialog rails are not counted here.
 */
export function countRails(data?: RailsConfigOutput): number {
  const rails = data?.rails;
  if (!rails) return 0;
  return (
    (rails.input?.flows?.length ?? 0) +
    (rails.output?.flows?.length ?? 0) +
    (rails.retrieval?.flows?.length ?? 0)
  );
}
