// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Button, Tag } from '@nvidia/foundations-react-core';
import type { InsightStatus } from '@studio/api/optimizer';
import type { ComponentProps } from 'react';

type TagColor = ComponentProps<typeof Tag>['color'];

/** Tag color per insight status. Exhaustive over InsightStatus. */
export const INSIGHT_STATUS_COLOR: Record<InsightStatus, TagColor> = {
  new: 'yellow',
  open: 'blue',
  resolved: 'green',
  rejected: 'red',
  closed: 'gray',
  deleted: 'gray',
};

export const insightStatusColor = (status: InsightStatus): TagColor =>
  INSIGHT_STATUS_COLOR[status] ?? 'gray';

/** A status-change action rendered as a button on the insight page. */
export interface InsightAction {
  label: string;
  /** Status the button transitions the insight to. */
  target: InsightStatus;
  kind: 'primary' | 'secondary';
  /** Optional button color; 'brand' renders the green primary CTA. */
  color?: ComponentProps<typeof Button>['color'];
}

// Canonical order: secondary actions first, Run experiment (green brand CTA) on the right.
const OPEN: InsightAction = {
  label: 'Run experiment',
  target: 'open',
  kind: 'primary',
  color: 'brand',
};
const REJECT: InsightAction = { label: 'Reject', target: 'rejected', kind: 'secondary' };
const CLOSE: InsightAction = { label: 'Close', target: 'closed', kind: 'secondary' };
const RESOLVE: InsightAction = { label: 'Resolve', target: 'resolved', kind: 'primary' };

/**
 * The status-change actions available for an insight in a given status.
 *
 * - new        → Reject, Run experiment (a new insight can't be closed)
 * - open       → Close, Resolve (no re-open; Resolve closes it)
 * - resolved / rejected / closed / deleted → Run experiment (re-open)
 */
export const insightActions = (status: InsightStatus): InsightAction[] => {
  switch (status) {
    case 'new':
      return [REJECT, OPEN];
    case 'open':
      return [CLOSE, RESOLVE];
    default:
      return [OPEN];
  }
};
