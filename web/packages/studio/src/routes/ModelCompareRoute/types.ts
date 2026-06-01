// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { InferenceParams } from '@studio/components/chat/params';

/** Color/label slots assigned by position. First panel is Baseline. */
export type PanelRoleColor = 'baseline' | 'cyan' | 'magenta' | 'amber';

export const PANEL_ROLE_COLORS: readonly PanelRoleColor[] = [
  'baseline',
  'cyan',
  'magenta',
  'amber',
];

export const PANEL_ROLE_LABELS: Record<PanelRoleColor, string> = {
  baseline: 'Baseline',
  cyan: 'Comparison 1',
  magenta: 'Comparison 2',
  amber: 'Comparison 3',
};

/** Tailwind class for the small colored status dot beside the panel label. */
export const PANEL_ROLE_DOT_CLASS: Record<PanelRoleColor, string> = {
  baseline: 'bg-fg-subdued',
  cyan: 'bg-accent-blue',
  magenta: 'bg-accent-purple',
  amber: 'bg-accent-orange',
};

/**
 * One entry in the shared "models we are comparing" list owned by ModelCompareRoute.
 * Children (Chat, Prompts) render based on this list but keep their own per-entry
 * ephemeral state (collapsed, chat history, response cells, etc.) keyed by id.
 *
 * `systemPrompt` and `params` live on the shared entry (not the per-view state)
 * because they should persist across the Chat / Run Prompts toggle. `locked`
 * is for the agent-context overlay where panel 0's model is fixed to the
 * agent's current model.
 */
export interface SharedModelEntry {
  id: number;
  /** Full URN, e.g. "abacusai/dracarys-llama-70b". Null means unassigned. */
  modelURN: string | null;
  systemPrompt: string;
  params: InferenceParams;
  /** False until the user opens Params and changes a value. When false we send
   *  no inference parameters and the provider applies its own defaults — this
   *  matters because some providers (e.g. Bedrock Claude Opus 4-7) reject
   *  `temperature` outright. */
  paramsTouched: boolean;
  locked?: boolean;
}

/** Shape consumed by ModelChatPanel — composed per-render from shared entry + local state. */
export interface PanelState {
  id: number;
  collapsed: boolean;
  /** Full model URN ("workspace/name"), or null if unassigned. */
  modelURN: string | null;
  systemPrompt: string;
  params: InferenceParams;
  paramsTouched: boolean;
  roleColor: PanelRoleColor;
  roleLabel: string;
  /** True when this is the only panel — drives the larger per-panel action bar. */
  isSinglePanel: boolean;
  locked: boolean;
}
