// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { IntakeAccordion } from '@nemo/common/src/components/IntakeAccordion';
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
  Badge,
  Button,
  Flex,
  SegmentedControl,
  Spinner,
  Stack,
  Text,
  Tooltip,
} from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { IntakeErrorBanner } from '@studio/components/IntakeDetail/IntakeComponents/IntakeErrorBanner';
import { IntakeTelemetryStatusBadge } from '@studio/components/IntakeDetail/IntakeComponents/IntakeTelemetryStatusBadge';
import { SpanFeedbackControls } from '@studio/components/IntakeDetail/IntakeComponents/SpanFeedbackControls';
import { getSpanTemplate } from '@studio/components/IntakeDetail/SpanTemplates/registry';
import { TraceSpanTree } from '@studio/components/IntakeDetail/TraceDetailSpanTree';
import { TraceSpanAccordionContent } from '@studio/components/IntakeDetail/TraceSpanAccordionContent';
import { SpanKindBadge } from '@studio/components/SpanKindBadge';
import {
  buildSpanHierarchyRows,
  buildSpanTree,
  formatCost,
  formatDurationMs,
  formatInteger,
  getSpanDisplayName,
  getSpanDurationMs,
  getSpansDurationMs,
  getSpanSubject,
  type SpanTableRow,
  type SpanTreeNode,
} from '@studio/util/intakeTelemetry';
import { useQueryClient } from '@tanstack/react-query';
import { ChevronsDownUp, ChevronsUpDown } from 'lucide-react';
import { type FC, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';

const TRACE_SPANS_PAGE_SIZE = 1000;
const HIERARCHY_SPACER_LIMIT = 12;

type ViewMode = 'tree' | 'list';

/** A pending "add note" request: which span to focus, plus a nonce that bumps on
 * every click so the same span can be re-targeted. */
type NoteRequest = { spanId: string; nonce: number } | null;

/** The focus nonce for a span, or undefined when it isn't the current target. */
const noteFocusNonce = (request: NoteRequest, spanId: string): number | undefined =>
  request?.spanId === spanId ? request.nonce : undefined;

/** DOM id for a span's accordion item, used to scroll it into view. */
const spanAccordionId = (spanId: string): string => `intake-span-${spanId}`;

// ── Shared row header (the span name/kind/subject + trailing metrics) ────────

const SpanTriggerLabel: FC<{ span: SpanTableRow; showHierarchy?: boolean }> = ({
  span,
  showHierarchy = true,
}) => {
  const depth = span.hierarchyDepth;
  const hierarchyLabel =
    !showHierarchy || span.hierarchyStatus === undefined
      ? undefined
      : span.hierarchyStatus === 'parent_outside_page'
        ? 'Parent outside page'
        : 'Unresolved hierarchy';

  return (
    <>
      {showHierarchy &&
        Array.from({ length: Math.min(depth, HIERARCHY_SPACER_LIMIT) }).map((_, index) => (
          <span
            key={`${span.span_id}-hierarchy-spacer-${index}`}
            aria-hidden
            className="w-[18px] shrink-0"
          />
        ))}
      {showHierarchy && depth > 0 && (
        <span aria-hidden className="relative h-5 w-5 shrink-0">
          <span className="absolute left-0 top-1/2 w-full border-t border-base" />
          <span className="absolute left-0 top-0 h-1/2 border-l border-base" />
        </span>
      )}
      <Text kind="body/semibold/sm" className="shrink-0 truncate font-mono">
        {getSpanTemplate(span.kind).headerTitle?.(span) ?? getSpanDisplayName(span)}
      </Text>
      <SpanKindBadge kind={span.kind} />
      <Text kind="body/regular/sm" className="min-w-0 flex-1 truncate text-secondary">
        {getSpanSubject(span)}
      </Text>
      {hierarchyLabel && (
        <Text kind="body/regular/xs" className="shrink-0 text-secondary">
          {hierarchyLabel}
        </Text>
      )}
    </>
  );
};

// Compact unit-suffixed metric (e.g. "9tk", "3.50s"); the key name is the tooltip.
const SpanTriggerMetaValue: FC<{ label: string; value: string }> = ({ label, value }) => (
  <Tooltip slotContent={label} side="top">
    <Text
      kind="body/regular/xs"
      className="font-mono tabular-nums text-secondary whitespace-nowrap"
    >
      {value}
    </Text>
  </Tooltip>
);

/** Right-aligned token/cost/duration metrics; key names surface as tooltips. */
const SpanTriggerMeta: FC<{ span: SpanTableRow }> = ({ span }) => {
  // A template may surface a kind-specific metric (e.g. an evaluator score or
  // guardrail decision) alongside the latency.
  const headerBadge = getSpanTemplate(span.kind).headerBadge?.(span);

  return (
    <>
      {span.status && span.status !== 'success' && (
        <IntakeTelemetryStatusBadge status={span.status} />
      )}
      <Flex align="center" gap="density-xl">
        {span.total_tokens !== null && span.total_tokens !== undefined && (
          <SpanTriggerMetaValue
            label="Total Tokens"
            value={`${formatInteger(span.total_tokens)}tk`}
          />
        )}
        {span.cost_total_usd !== null && span.cost_total_usd !== undefined && (
          <SpanTriggerMetaValue label="Total Cost" value={formatCost(span.cost_total_usd)} />
        )}
        {headerBadge !== undefined && (
          <Badge color={headerBadge.color ?? 'gray'} kind="solid">
            {headerBadge.text}
          </Badge>
        )}
        <SpanTriggerMetaValue
          label="Duration"
          value={formatDurationMs(getSpanDurationMs(span)).replace(/\s+/g, '')}
        />
      </Flex>
    </>
  );
};

// ── List view: every span as a collapsible accordion row (no tree) ───────────

interface SpanListViewProps {
  spanRows: SpanTableRow[];
  workspace: string;
  openSpanIds: string[];
  onValueChange: (next: string[]) => void;
  banner: ReactNode;
  feedbackBySpan: Map<string, FeedbackAnnotationInputValue>;
  annotationCountBySpan: Map<string, number>;
  noteRequest: NoteRequest;
  onAddNote: (spanId: string) => void;
}

const SpanListView: FC<SpanListViewProps> = ({
  spanRows,
  workspace,
  openSpanIds,
  onValueChange,
  banner,
  feedbackBySpan,
  annotationCountBySpan,
  noteRequest,
  onAddNote,
}) => (
  <Stack gap="density-lg" className="min-w-0">
    {banner}
    <div className="min-w-0 overflow-hidden rounded-lg bg-surface-raised">
      <IntakeAccordion
        variant="row"
        value={openSpanIds}
        onValueChange={onValueChange}
        items={spanRows.map((span) => ({
          value: span.span_id,
          id: spanAccordionId(span.span_id),
          slotLabel: <SpanTriggerLabel span={span} />,
          slotEnd: (
            <>
              <SpanTriggerMeta span={span} />
              <SpanFeedbackControls
                workspace={workspace}
                spanId={span.span_id}
                sessionId={span.session_id}
                activeFeedback={feedbackBySpan.get(span.span_id)}
                annotationCount={annotationCountBySpan.get(span.span_id)}
                onAddNote={() => onAddNote(span.span_id)}
              />
            </>
          ),
          slotContent: openSpanIds.includes(span.span_id) ? (
            <TraceSpanAccordionContent
              workspace={workspace}
              spanId={span.span_id}
              summarySpan={span}
              annotationCount={annotationCountBySpan.get(span.span_id)}
              focusNoteNonce={noteFocusNonce(noteRequest, span.span_id)}
            />
          ) : null,
        }))}
      />
    </div>
  </Stack>
);

// ── Tree view: trajectory tree on the left, the selected span on the right ───

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

const SpanTreeView: FC<SpanTreeViewProps> = ({
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
