// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Button, Flex, SegmentedControl } from '@nvidia/foundations-react-core';
import type { ResolvedPluginTraceView } from '@studio/plugins/PluginTraceViewContext';
import { PluginTraceViewActivity } from '@studio/plugins/PluginTraceViews';
import type { PluginTrace, PluginTraceViewMode } from '@studio/plugins/types';
import { ChevronsDownUp, ChevronsUpDown } from 'lucide-react';
import type { FC } from 'react';

export type TraceViewMode = 'tree' | 'list' | PluginTraceViewMode;

interface TraceViewToolbarProps {
  viewMode: TraceViewMode;
  onViewModeChange: (viewMode: TraceViewMode) => void;
  onCollapseAll?: () => void;
  onExpandAll?: () => void;
  pluginViews?: ResolvedPluginTraceView[];
  trace?: PluginTrace;
}

/** Shared Tree/List toolbar for session and trace-selected detail bodies. */
export const TraceViewToolbar: FC<TraceViewToolbarProps> = ({
  viewMode,
  onViewModeChange,
  onCollapseAll,
  onExpandAll,
  pluginViews = [],
  trace,
}) => (
  <Flex align="center" justify="between" gap="density-lg" className="min-w-0">
    <SegmentedControl
      size="tiny"
      value={viewMode}
      onValueChange={(value) => onViewModeChange(value as TraceViewMode)}
      items={[
        { value: 'tree', children: 'Tree' },
        { value: 'list', children: 'List' },
        ...pluginViews.map((view) => ({ value: view.mode, children: view.label })),
      ]}
    />
    <Flex align="center" justify="end" gap="density-sm" className="min-w-0">
      {trace
        ? pluginViews.map((view) => (
            <PluginTraceViewActivity key={view.mode} view={view} trace={trace} />
          ))
        : null}
      {(viewMode === 'tree' || viewMode === 'list') && onCollapseAll && onExpandAll ? (
        <Flex align="center" gap="density-xs">
          <Button
            kind="tertiary"
            size="tiny"
            type="button"
            aria-label="Collapse all"
            title="Collapse all"
            onClick={onCollapseAll}
          >
            <ChevronsDownUp size={14} aria-hidden />
          </Button>
          <Button
            kind="tertiary"
            size="tiny"
            type="button"
            aria-label="Expand all"
            title="Expand all"
            onClick={onExpandAll}
          >
            <ChevronsUpDown size={14} aria-hidden />
          </Button>
        </Flex>
      ) : null}
    </Flex>
  </Flex>
);
