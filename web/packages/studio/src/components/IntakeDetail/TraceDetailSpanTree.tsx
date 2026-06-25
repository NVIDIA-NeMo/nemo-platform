// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SpanStatus } from '@nemo/sdk/generated/platform/schema';
import {
  TreeNavBranch,
  TreeNavBranchTrigger,
  TreeNavLeaf,
  TreeNavList,
  TreeNavRoot,
} from '@nvidia/foundations-react-core';
import { getSpanTemplate } from '@studio/components/IntakeDetail/SpanTemplates/registry';
import { getSpanKindConfig } from '@studio/components/SpanKindBadge/spanKindConfig';
import {
  formatDurationMs,
  getSpanDisplayName,
  getSpanDurationMs,
  type SpanTreeNode,
} from '@studio/util/intakeTelemetry';
import { TriangleAlert, Workflow } from 'lucide-react';
import { type FC, type ReactNode } from 'react';

interface TraceSpanTreeProps {
  /** Span trajectory, nested by `parent_span_id` (see `buildSpanTree`). */
  nodes: SpanTreeNode[];
  /** Overall trace duration shown on the leading "Session" row. */
  sessionDurationMs?: number;
  /** Marks the "Session" row as errored when the trace failed. */
  sessionErrored?: boolean;
  /** Span currently highlighted in the tree (mirrors the open accordion). */
  activeSpanId: string | null;
  /** Fired when a span row is activated; opens/scrolls the matching accordion. */
  onSelectSpan: (spanId: string) => void;
  /** Fired when the leading "Session" row is activated; reloads the view. */
  onSelectSession?: () => void;
}

// Match the kind badge's accent color on the tree icon. KUI sets the icon color
// via `.nv-tree-nav-root svg` in Tailwind's `base` layer, so a utility class
// (the later `utilities` layer) wins without !important. Gray kinds (chain,
// unknown) have no accent and inherit KUI's default icon color.
const KIND_ICON_COLOR_CLASS: Record<string, string> = {
  teal: 'text-[color:var(--text-color-accent-teal)]',
  purple: 'text-[color:var(--text-color-accent-purple)]',
  blue: 'text-[color:var(--text-color-accent-blue)]',
  green: 'text-[color:var(--text-color-accent-green)]',
  yellow: 'text-[color:var(--text-color-accent-yellow)]',
};

// Tree rows: round the row highlight and add the vertical padding KUI omits.
const ROW_CLASS = 'rounded-[var(--radius-md)] py-[2px]';

const hierarchyTitle = (node: SpanTreeNode): string | undefined => {
  if (node.hierarchyStatus === 'parent_outside_page') return 'Parent span is outside this page';
  if (node.hierarchyStatus === 'cycle_or_unreachable') return 'Unresolved span hierarchy';
  return undefined;
};

interface SpanTreeLabelProps {
  name: string;
  durationMs?: number;
  errored?: boolean;
}

/** Shared label layout: name (truncates) + optional error badge + duration. */
const SpanTreeLabel: FC<SpanTreeLabelProps> = ({ name, durationMs, errored }) => (
  <span className="flex flex-1 items-center gap-2 min-w-0">
    <span className="flex-1 min-w-0 truncate">{name}</span>
    {errored && (
      <TriangleAlert
        role="img"
        aria-label="Error"
        fill="currentColor"
        // size-3.5 (14px) + accent-red as utilities, which win over KUI's base-layer svg rule.
        className="size-3.5 text-[color:var(--text-color-accent-red)]"
      />
    )}
    <span className="shrink-0 font-mono text-[length:var(--text-12)] tabular-nums text-[color:var(--text-color-secondary)]">
      {formatDurationMs(durationMs)}
    </span>
  </span>
);

const renderSpanNodes = (
  nodes: SpanTreeNode[],
  activeSpanId: string | null,
  onSelectSpan: (spanId: string) => void
): ReactNode =>
  nodes.map((node) => {
    const { span, children } = node;
    const kindConfig = getSpanKindConfig(span.kind);
    const Icon = kindConfig.icon;
    const icon = (
      <Icon role="img" aria-hidden className={KIND_ICON_COLOR_CLASS[kindConfig.color]} />
    );
    const active = activeSpanId === span.span_id;
    const title = hierarchyTitle(node);
    // Mirror the accordion/row header: a template may elevate a kind-specific
    // identity (e.g. the evaluator name) over the generic span name.
    const name = getSpanTemplate(span.kind).headerTitle?.(span) ?? getSpanDisplayName(span);
    const label = (
      <SpanTreeLabel
        name={name}
        durationMs={getSpanDurationMs(span)}
        errored={span.status === SpanStatus.error}
      />
    );

    if (children.length > 0) {
      return (
        <TreeNavBranch key={span.span_id} defaultOpen collapsible={false}>
          {/* Non-collapsible triggers suppress `onClick` in the KUI handler, so
              bind selection on the capture phase to keep branches always-open
              yet clickable. */}
          <TreeNavBranchTrigger
            className={ROW_CLASS}
            slotIcon={icon}
            active={active}
            title={title}
            onClickCapture={() => onSelectSpan(span.span_id)}
          >
            {label}
          </TreeNavBranchTrigger>
          <TreeNavList>{renderSpanNodes(children, activeSpanId, onSelectSpan)}</TreeNavList>
        </TreeNavBranch>
      );
    }

    return (
      <TreeNavLeaf
        key={span.span_id}
        className={ROW_CLASS}
        slotIcon={icon}
        active={active}
        title={title}
        onSelect={() => onSelectSpan(span.span_id)}
      >
        {label}
      </TreeNavLeaf>
    );
  });

/**
 * Hierarchical view of a trace's trajectory, rendered beside the span
 * accordions. Selecting a span highlights it here and opens/scrolls its
 * accordion; opening an accordion highlights the matching tree row.
 */
export const TraceSpanTree: FC<TraceSpanTreeProps> = ({
  nodes,
  sessionDurationMs,
  sessionErrored,
  activeSpanId,
  onSelectSpan,
  onSelectSession,
}) => (
  <TreeNavRoot aria-label="Trace trajectory" className="w-full">
    <TreeNavList>
      <TreeNavLeaf
        className={ROW_CLASS}
        slotIcon={<Workflow role="img" aria-hidden />}
        title="Reload trace"
        onSelect={onSelectSession}
      >
        <SpanTreeLabel name="Session" durationMs={sessionDurationMs} errored={sessionErrored} />
      </TreeNavLeaf>
      {renderSpanNodes(nodes, activeSpanId, onSelectSpan)}
    </TreeNavList>
  </TreeNavRoot>
);
