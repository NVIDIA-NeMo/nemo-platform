// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import {
  getGetTraceQueryKey,
  getListSpansQueryKey,
  useGetSpan,
  useListAnnotations,
  useListSpans,
} from '@nemo/sdk/generated/platform/api';
import {
  AnnotationSortField,
  type FeedbackAnnotationInputValue,
  SpanStatus,
  type Trace,
} from '@nemo/sdk/generated/platform/schema';
import {
  Button,
  Flex,
  SegmentedControl,
  Spinner,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { IntakeErrorBanner } from '@studio/components/IntakeDetail/IntakeComponents/IntakeErrorBanner';
import { SpanListView } from '@studio/components/IntakeDetail/TraceSpanListView';
import {
  type NoteRequest,
  noteFocusNonce,
  spanAccordionId,
} from '@studio/components/IntakeDetail/traceSpanShared';
import { SpanTreeView } from '@studio/components/IntakeDetail/TraceSpanTreeView';
import { QUERY_PARAMETERS } from '@studio/routes/constants';
import {
  buildSpanHierarchyRows,
  buildSpanTree,
  getSpansDurationMs,
} from '@studio/util/intakeTelemetry';
import { useQueryClient } from '@tanstack/react-query';
import { ChevronsDownUp, ChevronsUpDown } from 'lucide-react';
import { type FC, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

const TRACE_SPANS_PAGE_SIZE = 1000;

type ViewMode = 'tree' | 'list';

// ── Explorer: toolbar (Tree/List + expand/collapse) over the chosen view ─────

interface TraceSpanAccordionsProps {
  workspace: string;
  trace: Trace;
}

export const TraceSpanAccordions: FC<TraceSpanAccordionsProps> = ({ workspace, trace }) => {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const linkedSpanId = searchParams.get(QUERY_PARAMETERS.spanId) || null;
  const [viewMode, setViewMode] = useState<ViewMode>('tree');
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
    data: spansResponse,
    isFetching,
    error,
  } = useListSpans(workspace, {
    filter: { trace_id: trace.id },
    mode: 'summary',
    page: 1,
    page_size: TRACE_SPANS_PAGE_SIZE,
    sort: 'started_at',
  });

  const spans = spansResponse?.data;
  const spanRows = useMemo(() => buildSpanHierarchyRows(spans ?? []), [spans]);
  const spanTree = useMemo(() => buildSpanTree(spans ?? []), [spans]);
  const sessionDurationMs = useMemo(
    () => trace.duration_ms ?? getSpansDurationMs(spans ?? []),
    [trace.duration_ms, spans]
  );
  // Tree view shows one span at a time. Default to the first/root span when no
  // deep link is present, while preserving an out-of-page deep link for the
  // direct span detail fetch below.
  const selectedSpanFromPage = useMemo(
    () => (linkedSpanId ? spanRows.find((span) => span.span_id === linkedSpanId) : spanRows[0]),
    [spanRows, linkedSpanId]
  );
  const shouldFetchLinkedSpan =
    linkedSpanId !== null && spans !== undefined && selectedSpanFromPage === undefined;
  const {
    data: linkedSpanDetail,
    error: linkedSpanError,
    isLoading: isLinkedSpanLoading,
  } = useGetSpan(workspace, linkedSpanId ?? '', {
    query: { enabled: shouldFetchLinkedSpan },
  });
  const linkedSpanMatchesTrace =
    linkedSpanDetail === undefined ||
    linkedSpanDetail.trace_id === undefined ||
    linkedSpanDetail.trace_id === trace.id;
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
    () => spanRows.find((span) => span.span_id === trace.root_span_id) ?? spanRows[0],
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
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (spanId) next.set(QUERY_PARAMETERS.spanId, spanId);
          else next.delete(QUERY_PARAMETERS.spanId);
          return next;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  const handleSelectSpan = useCallback(
    (spanId: string) => {
      scrollToActiveRef.current = true;
      updateLinkedSpanId(spanId);
      setOpenSpanIds((open) => (open.includes(spanId) ? open : [...open, spanId]));
    },
    [updateLinkedSpanId]
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
    (value: string) => {
      const nextViewMode = value as ViewMode;
      setViewMode(nextViewMode);
      if (nextViewMode === 'list' && selectedSpanId) {
        setOpenSpanIds((open) =>
          open.includes(selectedSpanId) ? open : [...open, selectedSpanId]
        );
      }
    },
    [selectedSpanId]
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
    if (selectedSpanId && linkedSpanId !== selectedSpanId) {
      updateLinkedSpanId(selectedSpanId);
    }
    if (selectedSpanId && scrollToActiveRef.current) {
      scrollToActiveRef.current = false;
      document
        .getElementById(spanAccordionId(selectedSpanId))
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [linkedSpanId, selectedSpanId, updateLinkedSpanId]);

  // Clicking the tree's "Session" root reloads the view: return to the
  // default span, close every accordion, scroll to top, and refetch trace data.
  const handleReloadSession = useCallback(() => {
    scrollToActiveRef.current = false;
    updateLinkedSpanId(null);
    setOpenSpanIds([]);
    void queryClient.invalidateQueries({ queryKey: getGetTraceQueryKey(workspace, trace.id) });
    void queryClient.invalidateQueries({ queryKey: getListSpansQueryKey(workspace) });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [queryClient, updateLinkedSpanId, workspace, trace.id]);

  const showSpanLimitMessage =
    trace.span_count !== undefined &&
    trace.span_count !== null &&
    trace.span_count > TRACE_SPANS_PAGE_SIZE;

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

  if (error) {
    return <ErrorMessage message={getErrorMessage(error)} />;
  }

  return (
    <Stack gap="density-lg" className="min-w-0">
      <Flex align="center" justify="between" gap="density-lg" className="min-w-0">
        <SegmentedControl
          size="tiny"
          value={viewMode}
          onValueChange={handleViewModeChange}
          items={[
            { value: 'tree', children: 'Tree' },
            { value: 'list', children: 'List' },
          ]}
        />
        {spanRows.length > 0 && (
          <Flex align="center" gap="density-xs">
            <Button
              kind="tertiary"
              size="tiny"
              type="button"
              aria-label="Collapse all"
              title="Collapse all"
              onClick={collapseAll}
            >
              <ChevronsDownUp size={14} aria-hidden />
            </Button>
            <Button
              kind="tertiary"
              size="tiny"
              type="button"
              aria-label="Expand all"
              title="Expand all"
              onClick={expandAll}
            >
              <ChevronsUpDown size={14} aria-hidden />
            </Button>
          </Flex>
        )}
      </Flex>

      {showSpanLimitMessage && (
        <Text kind="body/regular/sm" className="text-secondary">
          Showing first {TRACE_SPANS_PAGE_SIZE.toLocaleString()} of{' '}
          {trace.span_count?.toLocaleString()} spans. Parent spans outside this page are marked in
          the hierarchy.
        </Text>
      )}

      {isFetching && spanRows.length === 0 ? (
        <Flex align="center" justify="center" className="min-h-[200px]">
          <Spinner size="medium" aria-label="Loading spans" />
        </Flex>
      ) : spanRows.length === 0 && !shouldFetchLinkedSpan ? (
        <Text kind="body/regular/sm" className="text-secondary">
          No spans were found for this trace.
        </Text>
      ) : viewMode === 'tree' ? (
        <SpanTreeView
          spanTree={spanTree}
          selectedSpan={selectedSpan}
          workspace={workspace}
          sessionDurationMs={sessionDurationMs}
          sessionErrored={trace.status === SpanStatus.error}
          activeSpanId={selectedSpanId}
          onSelectSpan={handleSelectSpan}
          onSelectSession={handleReloadSession}
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
          emptyContent={linkedSpanStatusContent}
        />
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
