// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { LucideIcon } from 'lucide-react';

/** Visual status of a node, used to tint the card's leading icon. */
export type DagNodeStatus = 'idle' | 'running' | 'success' | 'error';

/** Presentational content rendered inside a card node. */
export interface DagNodeData {
  /** Primary label shown on the card. */
  title: string;
  /** Accent type label beneath the title (e.g. "LLM TEXT"). */
  type?: string;
  /** Muted one-line description below the header. */
  description?: string;
  /** Variable/parameter tokens rendered as monospace pills (e.g. `"{{topic}}"`). */
  tags?: string[];
  /** Leading icon shown in the card's icon badge. */
  icon?: LucideIcon;
  /** Optional status accent; defaults to `'idle'`. Tints the leading icon. */
  status?: DagNodeStatus;
  /**
   * Accent classes applied to the icon (when idle) and subtitle, e.g.
   * `text-[color:var(--text-color-accent-purple)]`. Non-idle statuses keep their
   * semantic feedback color on the icon regardless of this prop.
   */
  colorClassName?: string;
}

/** A single node in the DAG, identified by a unique `id`. */
export interface DagNode {
  id: string;
  data: DagNodeData;
}

/** A directed edge drawn as an arrow from `source` to `target` (by node id). */
export interface DagEdge {
  /** Optional id; defaults to `${source}->${target}`. */
  id?: string;
  source: string;
  target: string;
  /** Optional label rendered on the arrow. */
  label?: string;
}

/** Layout flow direction: top-to-bottom or left-to-right. */
export type DagDirection = 'TB' | 'LR';
