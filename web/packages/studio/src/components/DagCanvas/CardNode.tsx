// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CardIconBadge, SelectableCard } from '@studio/components/common/SelectableCard';
import type { DagNodeData, DagNodeStatus } from '@studio/components/DagCanvas/types';
import { Handle, type Node, type NodeProps, Position } from '@xyflow/react';
import { Box } from 'lucide-react';
import { type FC } from 'react';

/** Internal node data: the public {@link DagNodeData} plus the activation callback. */
export interface CardNodeData extends DagNodeData {
  /** Invoked when the card is clicked or activated via keyboard. */
  onActivate?: () => void;
  [key: string]: unknown;
}

export type CardNodeType = Node<CardNodeData, 'card'>;

/** Status → leading icon color, using NVIDIA Foundations feedback tokens. */
const STATUS_ICON_CLASS: Record<DagNodeStatus, string> = {
  idle: 'text-[color:var(--text-color-accent-blue)]',
  running: 'text-[color:var(--text-color-feedback-info)]',
  success: 'text-[color:var(--text-color-feedback-success)]',
  error: 'text-[color:var(--text-color-feedback-danger)]',
};

/**
 * A DAG node rendered as a {@link SelectableCard} — the same card the Data Designer
 * column palette uses — with an icon badge, an accent type label, a description, and
 * variable tags, plus React Flow connection handles on the leading/trailing edges.
 */
export const CardNode: FC<NodeProps<CardNodeType>> = ({
  data,
  selected,
  sourcePosition = Position.Bottom,
  targetPosition = Position.Top,
}) => {
  const {
    title,
    type,
    description,
    tags,
    icon: Icon = Box,
    status = 'idle',
    colorClassName,
    onActivate,
  } = data;
  const iconClassName =
    status === 'idle' && colorClassName ? colorClassName : STATUS_ICON_CLASS[status];
  return (
    <>
      <Handle type="target" position={targetPosition} className="bg-strong border-none" />
      <SelectableCard
        title={title}
        subtitle={type}
        subtitleClassName={`uppercase tracking-wide ${colorClassName ?? 'text-[color:var(--text-color-accent-blue)]'}`}
        description={description}
        tags={tags}
        selected={selected}
        onActivate={onActivate}
        leading={
          <CardIconBadge>
            <Icon size={16} className={iconClassName} aria-hidden />
          </CardIconBadge>
        }
      />
      <Handle type="source" position={sourcePosition} className="bg-strong border-none" />
    </>
  );
};
