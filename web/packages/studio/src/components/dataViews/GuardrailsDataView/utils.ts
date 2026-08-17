// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';

/**
 * Count the total number of configured rail flows across input, output, and
 * retrieval rails. Returns 0 if the config or rails are absent.
 *
 * Note: DialogRails does not expose a `flows` field in the SDK schema, so
 * dialog rails are not counted here.
 */
export function countRails(data?: RailsConfig): number {
  const rails = data?.rails;
  if (!rails) return 0;
  return (
    (rails.input?.flows?.length ?? 0) +
    (rails.output?.flows?.length ?? 0) +
    (rails.retrieval?.flows?.length ?? 0)
  );
}

/** Return the `model` field of the first model entry with type "main", or undefined. */
export function getMainModelName(data?: RailsConfig): string | undefined {
  return data?.models?.find((m) => m.type === 'main')?.model;
}

export interface RailCounts {
  input: number;
  output: number;
}

/** Return the number of configured input and output rail flows. */
export function getRailCounts(data?: RailsConfig): RailCounts {
  const rails = data?.rails;
  return {
    input: rails?.input?.flows?.length ?? 0,
    output: rails?.output?.flows?.length ?? 0,
  };
}
