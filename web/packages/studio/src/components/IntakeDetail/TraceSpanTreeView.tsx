// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FeedbackAnnotationInputValue } from '@nemo/sdk/generated/platform/schema';
import { Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { SpanFeedbackControls } from '@studio/components/IntakeDetail/IntakeComponents/SpanFeedbackControls';
import { SpanTriggerLabel } from '@studio/components/IntakeDetail/IntakeComponents/SpanTriggerLabel';
import { SpanTriggerMeta } from '@studio/components/IntakeDetail/IntakeComponents/SpanTriggerMeta';
import { TraceSpanTree } from '@studio/components/IntakeDetail/TraceDetailSpanTree';
import { TraceSpanAccordionContent } from '@studio/components/IntakeDetail/TraceSpanAccordionContent';
import type { SpanTableRow, SpanTreeNode } from '@studio/util/intakeTelemetry';
import type { FC, ReactNode } from 'react';

interface SpanTreeViewProps {
  spanTree: SpanTreeNode[];
  selectedSpan: SpanTableRow | undefined;
  workspace: string;
  sessionDurationMs?: number;
  sessionErrored: boolean;
  activeSpanId: string | null;
  onSelectSpan: (spanId: string) => void;
  onSelectSession: () => void;
  banner: ReactNode;
  expandToken: number;
  collapseToken: number;
  activeFeedback?: FeedbackAnnotationInputValue;
  annotationCount?: number;
  focusNoteNonce?: number;
  onAddNote: () => void;
}

/** Tree view: trajectory tree on the left, the selected span on the right. */
export const SpanTreeView: FC<SpanTreeViewProps> = ({
  spanTree,
  selectedSpan,
  workspace,
  sessionDurationMs,
  sessionErrored,
  activeSpanId,
  onSelectSpan,
  onSelectSession,
  banner,
  expandToken,
  collapseToken,
  activeFeedback,
  annotationCount,
  focusNoteNonce,
  onAddNote,
}) => (
  <Flex align="start" gap="density-md" className="min-w-0">
    <nav
      aria-label="Trace trajectory"
      className="sticky top-density-lg hidden max-h-[calc(100vh-6rem)] w-[18rem] shrink-0 self-start overflow-y-auto rounded-lg bg-surface-raised p-density-xs lg:block"
    >
      <TraceSpanTree
        nodes={spanTree}
        sessionDurationMs={sessionDurationMs}
        sessionErrored={sessionErrored}
        activeSpanId={activeSpanId ?? selectedSpan?.span_id ?? null}
        onSelectSpan={onSelectSpan}
        onSelectSession={onSelectSession}
      />
    </nav>
    <Stack gap="density-lg" className="min-w-0 flex-1">
      {banner}
      <div className="min-w-0 overflow-hidden rounded-lg bg-surface-raised">
        {selectedSpan ? (
          <>
            <Flex
              align="center"
              gap="density-lg"
              className="border-b border-base px-density-lg py-density-md min-w-0"
            >
              <span className="flex min-w-0 flex-1 items-center gap-density-sm">
                {/* No indentation: the selected span stands alone, not in a tree row. */}
                <SpanTriggerLabel span={selectedSpan} showHierarchy={false} />
              </span>
              <span className="flex shrink-0 items-center gap-density-lg">
                <SpanTriggerMeta span={selectedSpan} />
                <SpanFeedbackControls
                  workspace={workspace}
                  spanId={selectedSpan.span_id}
                  sessionId={selectedSpan.session_id}
                  activeFeedback={activeFeedback}
                  annotationCount={annotationCount}
                  onAddNote={onAddNote}
                />
              </span>
            </Flex>
            <div className="p-density-lg">
              <TraceSpanAccordionContent
                workspace={workspace}
                spanId={selectedSpan.span_id}
                summarySpan={selectedSpan}
                expandToken={expandToken}
                collapseToken={collapseToken}
                annotationCount={annotationCount}
                focusNoteNonce={focusNoteNonce}
              />
            </div>
          </>
        ) : (
          <Text kind="body/regular/sm" className="text-secondary p-density-lg">
            Select a span from the tree to view its details.
          </Text>
        )}
      </div>
    </Stack>
  </Flex>
);
