// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type {
  BroadcastSignal,
  ComposerMode,
} from '@nemo/common/src/components/AssistantChat/types';
import type { ReactNode } from 'react';

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

/** Seed payload used to pre-fill a panel's composer textarea from outside. */
export interface ComposerSeed {
  /** Monotonic counter — fires the pre-fill whenever it changes. */
  triggerCount: number;
  text: string;
}

/**
 * Broadcast/control props threaded from ModelCompareRoute down through
 * ModelCompareChat → ModelChatPanel → ModelChat. Extracted to avoid
 * repeating the same set in every intermediate interface.
 */
export interface PanelChatControls {
  composerMode?: ComposerMode;
  broadcast?: BroadcastSignal;
  stopCount?: number;
  onRunningChange?: (id: number, isRunning: boolean) => void;
  slotComposerEnd?: ReactNode;
  composerSeed?: ComposerSeed;
}

/** One entry in the shared "models we are comparing" list owned by ModelCompareRoute. */
export interface SharedModelEntry {
  id: number;
  /** Full URN, e.g. "abacusai/dracarys-llama-70b". Null means unassigned. */
  modelURN: string | null;
  locked?: boolean;
}

/** Shape consumed by ModelChatPanel — composed per-render from shared entry + local state. */
export interface PanelState {
  id: number;
  collapsed: boolean;
  /** Full model URN ("workspace/name"), or null if unassigned. */
  modelURN: string | null;
  roleColor: PanelRoleColor;
  roleLabel: string;
  /** True when this is the only panel — drives the larger per-panel action bar. */
  isSinglePanel: boolean;
  locked: boolean;
}
