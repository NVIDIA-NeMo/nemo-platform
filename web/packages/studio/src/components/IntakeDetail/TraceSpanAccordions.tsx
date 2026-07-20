// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import {
  type ListSpansQueryError,
  useGetSpan,
  useListAnnotations,
} from '@nemo/sdk/generated/platform/api';
import {
  AnnotationSortField,
  type FeedbackAnnotationInputValue,
  type Span,
  SpanStatus,
  type Trace,
} from '@nemo/sdk/generated/platform/schema';
import { Flex, Spinner, Stack, Text } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { IntakeErrorBanner } from '@studio/components/IntakeDetail/IntakeComponents/IntakeErrorBanner';
import { SpanListView } from '@studio/components/IntakeDetail/TraceSpanListView';
import {
  type NoteRequest,
  noteFocusNonce,
  spanAccordionId,
} from '@studio/components/IntakeDetail/traceSpanShared';
import { SpanTreeView } from '@studio/components/IntakeDetail/TraceSpanTreeView';
import {
  type TraceViewMode,
  TraceViewToolbar,
} from '@studio/components/IntakeDetail/TraceViewToolbar';
import { QUERY_PARAMETERS } from '@studio/routes/constants';
import {
  buildSpanHierarchyRows,
  getSpansDurationMs,
  type SessionTrajectory,
} from '@studio/util/intakeTelemetry';
import { type FC, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

const TRACE_SPANS_PAGE_SIZE = 1000;
const EMPTY_SPANS: Span[] = [];

// ── Explorer: toolbar (Tree/List + expand/collapse) over the chosen view ─────

interface TraceSpanAccordionsProps {
  workspace: string;
  trace: Trace;
  explorer: SessionExplorerData;
  onSelectSession: () => void;
  onSelectTrace: (traceId: string) => void;
  sessionDurationMs?: number;
  sessionErrored: boolean;
  viewMode: TraceViewMode;
  onViewModeChange: (viewMode: TraceViewMode) => void;
}

export interface SessionExplorerData {
  readonly trajectories: SessionTrajectory[];
  readonly spansLoaded: boolean;
  readonly spansError: ListSpansQueryError | null;
  readonly isSpansFetching: boolean;
  readonly spanPageSize: number;
  readonly spanTotal: number;
}

export const TraceSpanAccordions: FC<TraceSpanAccordionsProps> = ({
  workspace,
  trace,
  explorer,
  onSelectSession,
  onSelectTrace,
  sessionDurationMs,
  sessionErrored,
  viewMode,
  onViewModeChange,
}) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const linkedSpanId = searchParams.get(QUERY_PARAMETERS.spanId) || null;
  const [openSpanIds, setOpenSpanIds] = useState<string[]>([]);
  // Bumped to broadcast expand/collapse-all to the selected span's sections in
  // tree view (list view drives the span rows via `openSpanIds` instead).
  const [sectionExpandToken, setSectionExpandToken] = useState(0);
  const [sectionCollapseToken, setSectionCollapseToken] = useState(0);
  // The span whose annotations note field should open and focus, set when the
  // header's "add note" button is pressed.
  const [noteRequest, setNoteRequest] = useState<NoteRequest>(null);
  // Only scroll the accordion list when selection is driven from the tree, so
  // manually toggling an accordion doesn't yank the viewport around.
  const scrollToActiveRef = useRef(false);

  const {
    trajectories,
    spansLoaded,
    spansError,
    isSpansFetching,
    spanPageSize,
    spanTotal,
  } = explorer;
  const spans =
    trajectories.find(({ trace: sessionTrace }) => sessionTrace.id === trace.id)?.spans ??
    EMPTY_SPANS;

  const spanRows = useMemo(() => buildSpanHierarchyRows(spans), [spans]);
  const resolvedSessionDurationMs = useMemo(
    () => sessionDurationMs ?? trace.duration_ms ?? getSpansDurationMs(spans),
    [sessionDurationMs, trace.duration_ms, spans]
  );
  // Tree view shows one span at a time. Default to the first/root span when no
  // deep link is present, while preserving an out-of-page deep link for the
  // direct span detail fetch below.
  const selectedSpanFromPage = useMemo(
    () => (linkedSpanId ? spanRows.find((span) => span.span_id === linkedSpanId) : spanRows[0]),
    [spanRows, linkedSpanId]
  );
  const shouldFetchLinkedSpan =
    linkedSpanId !== null && spansLoaded && selectedSpanFromPage === undefined;
  const {
    data: linkedSpanDetail,
    error: linkedSpanError,
    isLoading: isLinkedSpanLoading,
  } = useGetSpan(workspace, linkedSpanId ?? '', {
    query: { enabled: shouldFetchLinkedSpan },
  });
  const linkedSpanMatchesTrace =
    linkedSpanDetail === undefined ||
    ((linkedSpanDetail.trace_id === undefined || linkedSpanDetail.trace_id === trace.id) &&
      linkedSpanDetail.session_id === trace.session_id);
  const linkedSpanFromDetail = useMemo(
    () =>
      linkedSpanDetail && linkedSpanMatchesTrace
        ? ({
            ...linkedSpanDetail,
            hierarchyDepth: 0,
            hierarchyStatus: 'parent_outside_page',
          } as const)
        : undefined,
    [linkedSpanDetail, linkedSpanMatchesTrace]
  );
  const selectedSpan = selectedSpanFromPage ?? linkedSpanFromDetail;
  const selectedSpanId = selectedSpan?.span_id ?? null;
  const listSpanRows = useMemo(
    () => (linkedSpanFromDetail ? [linkedSpanFromDetail, ...spanRows] : spanRows),
    [linkedSpanFromDetail, spanRows]
  );
  // The trace's own error lives on its root span (the trace status derives from
  // it); used to decide whether to surface a trace-level error banner.
  const rootSpan = useMemo(
    () => spanRows.find((span) => span.span_id === trace.root_span_id),
    [spanRows, trace.root_span_id]
  );

  // One query for the whole trace's annotations (rather than per row) so each
  // header can show its feedback sentiment and annotation count. Sorted
  // newest-first; keep the latest feedback per span.
  const { data: annotationsResponse } = useListAnnotations(workspace, {
    page: 1,
    page_size: TRACE_SPANS_PAGE_SIZE,
    sort: AnnotationSortField['-created_at'],
    filter: { session_id: trace.session_id },
  });
  const { feedbackBySpan, annotationCountBySpan, notesBySpan } = useMemo(() => {
    const feedback = new Map<string, FeedbackAnnotationInputValue>();
    const counts = new Map<string, number>();
    const notes = new Set<string>();
    for (const annotation of annotationsResponse?.data ?? []) {
      if (!annotation.span_id) continue;
      counts.set(annotation.span_id, (counts.get(annotation.span_id) ?? 0) + 1);
      if (annotation.kind === 'note') notes.add(annotation.span_id);
      if (annotation.kind === 'feedback' && !feedback.has(annotation.span_id)) {
        feedback.set(annotation.span_id, annotation.value);
      }
    }
    return { feedbackBySpan: feedback, annotationCountBySpan: counts, notesBySpan: notes };
  }, [annotationsResponse]);

  const updateLinkedSpanId = useCallback(
    (spanId: string | null) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (spanId) next.set(QUERY_PARAMETERS.spanId, spanId);
        else next.delete(QUERY_PARAMETERS.spanId);
        return next;
      });
    },
    [setSearchParams]
  );

  const handleSelectSpan = useCallback(
    (spanId: string, targetTraceId: string) => {
      scrollToActiveRef.current = true;
      setSearchParams((previous) => {
        const next = new URLSearchParams(previous);
        next.set(QUERY_PARAMETERS.traceId, targetTraceId);
        next.set(QUERY_PARAMETERS.spanId, spanId);
        return next;
      });
      setOpenSpanIds((open) => (open.includes(spanId) ? open : [...open, spanId]));
    },
    [setSearchParams]
  );

  const handleAccordionChange = useCallback(
    (next: string[]) => {
      const opened = next.find((id) => !openSpanIds.includes(id));
      if (opened) updateLinkedSpanId(opened);
      setOpenSpanIds(next);
    },
    [openSpanIds, updateLinkedSpanId]
  );

  const handleViewModeChange = useCallback(
    (nextViewMode: TraceViewMode) => {
      onViewModeChange(nextViewMode);
      if (nextViewMode === 'list' && selectedSpanId) {
        setOpenSpanIds((open) =>
          open.includes(selectedSpanId) ? open : [...open, selectedSpanId]
        );
      }
    },
    [onViewModeChange, selectedSpanId]
  );

  // In list view, expand/collapse opens every span row; in tree view it opens
  // every section of the one selected span.
  const expandAll = useCallback(() => {
    if (viewMode === 'list') setOpenSpanIds(listSpanRows.map((span) => span.span_id));
    else setSectionExpandToken((token) => token + 1);
  }, [viewMode, listSpanRows]);
  const collapseAll = useCallback(() => {
    if (viewMode === 'list') setOpenSpanIds([]);
    else setSectionCollapseToken((token) => token + 1);
  }, [viewMode]);

  // "Add note" reveals the span (selecting it in tree view, expanding its row in
  // list view) and bumps the nonce so its annotations panel opens and focuses
  // the note field.
  const handleAddNote = useCallback(
    (spanId: string) => {
      updateLinkedSpanId(spanId);
      setOpenSpanIds((open) => (open.includes(spanId) ? open : [...open, spanId]));
      setNoteRequest((prev) => ({ spanId, nonce: (prev?.nonce ?? 0) + 1 }));
    },
    [updateLinkedSpanId]
  );

  useEffect(() => {
    if (selectedSpanId && scrollToActiveRef.current) {
      scrollToActiveRef.current = false;
      document
        .getElementById(spanAccordionId(selectedSpanId))
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [selectedSpanId]);

  const showSpanLimitMessage = spanTotal > spanPageSize;

  // Only surface a trace-level error banner when the trace itself has an error
  // message (carried on its root span). A child-span error alone no longer
  // raises a banner here — it shows on that span's own detail instead.
  const banner = rootSpan?.error_message?.trim() ? (
    <IntakeErrorBanner
      heading={rootSpan.error_type?.trim() || 'Error'}
      message={rootSpan.error_message}
    />
  ) : null;

  const linkedSpanStatusContent =
    shouldFetchLinkedSpan && (isLinkedSpanLoading || linkedSpanError || !linkedSpanMatchesTrace) ? (
      <div className="p-density-lg">
        {isLinkedSpanLoading ? (
          <Flex align="center" justify="center" className="min-h-[200px]">
            <Spinner size="medium" aria-label="Loading linked span" />
          </Flex>
        ) : linkedSpanError ? (
          <ErrorMessage message={getErrorMessage(linkedSpanError)} />
        ) : !linkedSpanMatchesTrace ? (
          <ErrorMessage message="The linked span does not belong to this trace." />
        ) : null}
      </div>
    ) : undefined;
  const spansStatusContent = spansError ? (
    <div className="min-h-[200px] p-density-lg">
      <ErrorMessage message={getErrorMessage(spansError)} />
    </div>
  ) : isSpansFetching && spanRows.length === 0 ? (
    <Flex align="center" justify="center" className="min-h-[200px]">
      <Spinner size="medium" aria-label="Loading spans" />
    </Flex>
  ) : spanRows.length === 0 && !shouldFetchLinkedSpan ? (
    <Text kind="body/regular/sm" className="text-secondary p-density-lg">
      No spans were found for this trace.
    </Text>
  ) : undefined;

  return (
    <Stack gap="density-lg" className="min-w-0">
      <TraceViewToolbar
        viewMode={viewMode}
        onViewModeChange={handleViewModeChange}
        onCollapseAll={spanRows.length > 0 ? collapseAll : undefined}
        onExpandAll={spanRows.length > 0 ? expandAll : undefined}
      />

      {showSpanLimitMessage && (
        <Text kind="body/regular/sm" className="text-secondary">
          Showing first {spanPageSize.toLocaleString()} of {spanTotal.toLocaleString()} spans in
          this session. Parent spans outside this page are marked in the hierarchy.
        </Text>
      )}

      {viewMode === 'tree' ? (
        <SpanTreeView
          trajectories={trajectories}
          activeTraceId={trace.id}
          selectedSpan={selectedSpan}
          workspace={workspace}
          sessionDurationMs={resolvedSessionDurationMs}
          sessionErrored={sessionErrored || trace.status === SpanStatus.error}
          activeSpanId={linkedSpanId}
          onSelectSpan={handleSelectSpan}
          onSelectTrace={onSelectTrace}
          onSelectSession={onSelectSession}
          banner={banner}
          expandToken={sectionExpandToken}
          collapseToken={sectionCollapseToken}
          activeFeedback={selectedSpan ? feedbackBySpan.get(selectedSpan.span_id) : undefined}
          annotationCount={
            selectedSpan ? annotationCountBySpan.get(selectedSpan.span_id) : undefined
          }
          hasNotes={selectedSpan ? notesBySpan.has(selectedSpan.span_id) : false}
          focusNoteNonce={
            selectedSpan ? noteFocusNonce(noteRequest, selectedSpan.span_id) : undefined
          }
          onAddNote={() => selectedSpan && handleAddNote(selectedSpan.span_id)}
          emptyContent={spansStatusContent ?? linkedSpanStatusContent}
        />
      ) : spansStatusContent ? (
        spansStatusContent
      ) : (
        <SpanListView
          spanRows={listSpanRows}
          workspace={workspace}
          openSpanIds={openSpanIds}
          onValueChange={handleAccordionChange}
          banner={
            <>
              {banner}
              {linkedSpanStatusContent}
            </>
          }
          feedbackBySpan={feedbackBySpan}
          annotationCountBySpan={annotationCountBySpan}
          notesBySpan={notesBySpan}
          noteRequest={noteRequest}
          onAddNote={handleAddNote}
        />
      )}
    </Stack>
  );
};
