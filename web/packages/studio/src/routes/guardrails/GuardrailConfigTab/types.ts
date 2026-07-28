// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfigDataOutput } from '@nemo/sdk/generated/platform/schema';

/** A provider key under `rails.config.*` (e.g. `content_safety`, `gliner`). */
export type DetectorKey = keyof RailsConfigDataOutput;

/** A lifecycle stage in the guardrail pipeline, in execution order. */
export type StageKey =
  | 'input'
  | 'dialog'
  | 'retrieval'
  | 'output'
  | 'tool_input'
  | 'tool_output'
  | 'actions';

/** A stage a detector can run at (the flow-bearing subset of {@link StageKey}). */
export type Scope = 'input' | 'output' | 'retrieval' | 'tool_input' | 'tool_output';

/** A single label/value row rendered in a definition list. */
export interface Field {
  label: string;
  value: string;
}
