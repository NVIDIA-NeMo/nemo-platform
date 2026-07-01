// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { BadgeProps } from '@nvidia/foundations-react-core';
import type { AddColumnSelection } from '@studio/components/AddColumnPalette/types';
import type { LucideIcon } from 'lucide-react';

/** The four ways to start a Data Designer fileset shown as tiles on the new-fileset view. */
export type StartOptionId = 'ai' | 'template' | 'clone' | 'scratch';

export interface StartOptionTag {
  label: string;
  color: NonNullable<BadgeProps['color']>;
  kind: NonNullable<BadgeProps['kind']>;
}

export interface StartOption {
  id: StartOptionId;
  /** Tile title. */
  title: string;
  /** One-line tile description. */
  description: string;
  /** Leading Lucide icon. */
  icon: LucideIcon;
  /** Small badge rendered at the bottom of the tile. */
  tag?: StartOptionTag;
  /**
   * Whether this option is wired up. Disabled options still render (so the full set
   * of future entry points is visible) but are no-ops — they cannot be selected and
   * never reveal a detail panel or the Continue footer.
   */
  enabled: boolean;
}

/**
 * One column a template preloads onto the build canvas: which catalog option to create
 * (via `columnType`/`samplerType`), the column name other columns reference, and the
 * field values to seed. Resolved to a `BuilderColumn` by the build route.
 */
export interface TemplateColumnSpec extends AddColumnSelection {
  /** The column name (Jinja2 identifier); referenced by later columns via `{{ name }}`. */
  name: string;
  /** Field values keyed by `ColumnField.key`. Omit for columns with no seeded fields. */
  values?: Record<string, string>;
}

/**
 * A ready-made recipe shown as a card in the secondary area when the "Start from a
 * template" option is selected. Picking one preloads the build canvas with its columns.
 */
export interface FilesetTemplate {
  /** Stable id passed to {@link CreateFilesetStartProps.onContinue} when chosen. */
  id: string;
  /** Card title. */
  title: string;
  /** One- to two-line summary of what the recipe produces. */
  description: string;
  /** Leading Lucide icon. */
  icon: LucideIcon;
  /** Small badge (typically the use case) rendered at the bottom of the card. */
  tag: StartOptionTag;
  /** The columns preloaded onto the canvas, in order, when this template is chosen. */
  columns: TemplateColumnSpec[];
}
