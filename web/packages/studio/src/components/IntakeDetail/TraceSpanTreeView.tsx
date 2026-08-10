// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FeedbackAnnotationInputValue } from '@nemo/sdk/generated/platform/schema';
import { Flex, Text } from '@nvidia/foundations-react-core';
import { SpanFeedbackControls } from '@studio/components/IntakeDetail/IntakeComponents/SpanFeedbackControls';
import { SpanTriggerLabel } from '@studio/components/IntakeDetail/IntakeComponents/SpanTriggerLabel';
import { SpanTriggerMeta } from '@studio/components/IntakeDetail/IntakeComponents/SpanTriggerMeta';
import { TraceDetailLayout } from '@studio/components/IntakeDetail/TraceDetailLayout';
import { TraceSpanTree } from '@studio/components/IntakeDetail/TraceDetailSpanTree';
import { TraceSpanAccordionContent } from '@studio/components/IntakeDetail/TraceSpanAccordionContent';
import type { SessionTrajectory, SpanTableRow } from '@studio/util/intakeTelemetry';
import type { FC, ReactNode } from 'react';

interface SpanTreeViewProps {
  trajectories: SessionTrajectory[];
  activeTraceId: string;
  selectedSpan: SpanTableRow | undefined;
  workspace: string;
  sessionDurationMs?: number;
  sessionErrored: boolean;
  activeSpanId: string | null;
  onSelectSpan: (spanId: string, traceId: string) => void;
  onSelectTrace: (traceId: string) => void;
  onSelectSession: () => void;
  banner: ReactNode;
  expandToken: number;
  collapseToken: number;
  activeFeedback?: FeedbackAnnotationInputValue;
  annotationCount?: number;
  hasNotes?: boolean;
  focusNoteNonce?: number;
  onAddNote: () => void;
  emptyContent?: ReactNode;
}

/** Tree view: trajectory tree on the left, the selected span on the right. */
export const SpanTreeView: FC<SpanTreeViewProps> = ({
  trajectories,
  activeTraceId,
  selectedSpan,
  workspace,
  sessionDurationMs,
  sessionErrored,
  activeSpanId,
  onSelectSpan,
  onSelectTrace,
  onSelectSession,
  banner,
  expandToken,
  collapseToken,
  activeFeedback,
  annotationCount,
  hasNotes,
  focusNoteNonce,
  onAddNote,
  emptyContent,
}) => (
  <TraceDetailLayout
    navigation={
      <TraceSpanTree
        trajectories={trajectories}
        activeTraceId={activeTraceId}
        sessionDurationMs={sessionDurationMs}
        sessionErrored={sessionErrored}
        activeSpanId={activeSpanId}
        onSelectSpan={onSelectSpan}
        onSelectTrace={onSelectTrace}
        onSelectSession={onSelectSession}
      />
    }
  >
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
                hasNotes={hasNotes}
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
        (emptyContent ?? (
          <Text kind="body/regular/sm" className="text-secondary p-density-lg">
            Select a span from the tree to view its details.
          </Text>
        ))
      )}
    </div>
  </TraceDetailLayout>
);
