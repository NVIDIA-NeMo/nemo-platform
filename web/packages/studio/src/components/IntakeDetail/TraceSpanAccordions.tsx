// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import {
  getGetTraceQueryKey,
  getListSpansQueryKey,
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
import {
  buildSpanHierarchyRows,
  buildSpanTree,
  getSpansDurationMs,
} from '@studio/util/intakeTelemetry';
import { useQueryClient } from '@tanstack/react-query';
import { ChevronsDownUp, ChevronsUpDown } from 'lucide-react';
import { type FC, useCallback, useEffect, useMemo, useRef, useState } from 'react';

const TRACE_SPANS_PAGE_SIZE = 1000;

type ViewMode = 'tree' | 'list';

// ── Explorer: toolbar (Tree/List + expand/collapse) over the chosen view ─────

interface TraceSpanAccordionsProps {
  workspace: string;
  trace: Trace;
}

export const TraceSpanAccordions: FC<TraceSpanAccordionsProps> = ({ workspace, trace }) => {
  const queryClient = useQueryClient();
  const [viewMode, setViewMode] = useState<ViewMode>('tree');
  const [openSpanIds, setOpenSpanIds] = useState<string[]>([]);
  const [activeSpanId, setActiveSpanId] = useState<string | null>(null);
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
    // `detailed` so kind templates can read `raw_attributes` for the row header
    // (e.g. the evaluator name/score). Heavier than `summary` for very large
    // traces; revisit if span counts grow.
    mode: 'detailed',
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
  // Tree view shows one span at a time; default to the first (root) span.
  const selectedSpan = useMemo(
    () => spanRows.find((span) => span.span_id === activeSpanId) ?? spanRows[0],
    [spanRows, activeSpanId]
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
  const { feedbackBySpan, annotationCountBySpan } = useMemo(() => {
    const feedback = new Map<string, FeedbackAnnotationInputValue>();
    const counts = new Map<string, number>();
    for (const annotation of annotationsResponse?.data ?? []) {
      if (!annotation.span_id) continue;
      counts.set(annotation.span_id, (counts.get(annotation.span_id) ?? 0) + 1);
      if (annotation.kind === 'feedback' && !feedback.has(annotation.span_id)) {
        feedback.set(annotation.span_id, annotation.value);
      }
    }
    return { feedbackBySpan: feedback, annotationCountBySpan: counts };
  }, [annotationsResponse]);

  const handleSelectSpan = useCallback((spanId: string) => {
    scrollToActiveRef.current = true;
    setActiveSpanId(spanId);
    setOpenSpanIds((open) => (open.includes(spanId) ? open : [...open, spanId]));
  }, []);

  const handleAccordionChange = useCallback(
    (next: string[]) => {
      const opened = next.find((id) => !openSpanIds.includes(id));
      if (opened) setActiveSpanId(opened);
      setOpenSpanIds(next);
    },
    [openSpanIds]
  );

  // In list view, expand/collapse opens every span row; in tree view it opens
  // every section of the one selected span.
  const expandAll = useCallback(() => {
    if (viewMode === 'list') setOpenSpanIds(spanRows.map((span) => span.span_id));
    else setSectionExpandToken((token) => token + 1);
  }, [viewMode, spanRows]);
  const collapseAll = useCallback(() => {
    if (viewMode === 'list') setOpenSpanIds([]);
    else setSectionCollapseToken((token) => token + 1);
  }, [viewMode]);

  // "Add note" reveals the span (selecting it in tree view, expanding its row in
  // list view) and bumps the nonce so its annotations panel opens and focuses
  // the note field.
  const handleAddNote = useCallback((spanId: string) => {
    setActiveSpanId(spanId);
    setOpenSpanIds((open) => (open.includes(spanId) ? open : [...open, spanId]));
    setNoteRequest((prev) => ({ spanId, nonce: (prev?.nonce ?? 0) + 1 }));
  }, []);

  useEffect(() => {
    if (!activeSpanId || !scrollToActiveRef.current) return;
    scrollToActiveRef.current = false;
    document
      .getElementById(spanAccordionId(activeSpanId))
      ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [activeSpanId]);

  // Clicking the tree's "Session" root reloads the view: reset selection, close
  // every accordion, scroll to the top, and refetch the trace + span data.
  const handleReloadSession = useCallback(() => {
    scrollToActiveRef.current = false;
    setActiveSpanId(null);
    setOpenSpanIds([]);
    void queryClient.invalidateQueries({ queryKey: getGetTraceQueryKey(workspace, trace.id) });
    void queryClient.invalidateQueries({ queryKey: getListSpansQueryKey(workspace) });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [queryClient, workspace, trace.id]);

  const showSpanLimitMessage =
    trace.span_count !== undefined &&
    trace.span_count !== null &&
    trace.span_count > TRACE_SPANS_PAGE_SIZE;

  const banner =
    trace.status === SpanStatus.error ? (
      <IntakeErrorBanner
        heading="Error"
        message={
          trace.error_count
            ? `${trace.error_count} error span${trace.error_count === 1 ? '' : 's'} in this trace.`
            : 'This trace ended with an error.'
        }
      />
    ) : null;

  if (error) {
    return <ErrorMessage message={getErrorMessage(error)} />;
  }

  return (
    <Stack gap="density-lg" className="min-w-0">
      <Flex align="center" justify="between" gap="density-lg" className="min-w-0">
        <SegmentedControl
          size="tiny"
          value={viewMode}
          onValueChange={(value) => setViewMode(value as ViewMode)}
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
      ) : spanRows.length === 0 ? (
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
          activeSpanId={activeSpanId}
          onSelectSpan={handleSelectSpan}
          onSelectSession={handleReloadSession}
          banner={banner}
          expandToken={sectionExpandToken}
          collapseToken={sectionCollapseToken}
          activeFeedback={selectedSpan ? feedbackBySpan.get(selectedSpan.span_id) : undefined}
          annotationCount={
            selectedSpan ? annotationCountBySpan.get(selectedSpan.span_id) : undefined
          }
          focusNoteNonce={
            selectedSpan ? noteFocusNonce(noteRequest, selectedSpan.span_id) : undefined
          }
          onAddNote={() => selectedSpan && handleAddNote(selectedSpan.span_id)}
        />
      ) : (
        <SpanListView
          spanRows={spanRows}
          workspace={workspace}
          openSpanIds={openSpanIds}
          onValueChange={handleAccordionChange}
          banner={banner}
          feedbackBySpan={feedbackBySpan}
          annotationCountBySpan={annotationCountBySpan}
          noteRequest={noteRequest}
          onAddNote={handleAddNote}
        />
      )}
    </Stack>
  );
};
