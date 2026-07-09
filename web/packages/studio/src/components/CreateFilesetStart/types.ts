// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { BadgeProps } from '@nvidia/foundations-react-core';
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
