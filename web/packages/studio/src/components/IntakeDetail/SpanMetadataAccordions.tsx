// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  IntakeAccordion,
  type IntakeAccordionItem,
} from '@nemo/common/src/components/IntakeAccordion';
import { KeyValueGrid } from '@nemo/common/src/components/KeyValueGrid';
import { SpanStatus, type Span } from '@nemo/sdk/generated/platform/schema';
import { Badge, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { AnnotationsPanel } from '@studio/components/IntakeDetail/IntakeComponents/AnnotationsPanel';
import { IntakeErrorBanner } from '@studio/components/IntakeDetail/IntakeComponents/IntakeErrorBanner';
import { KeyValueRows } from '@studio/components/IntakeDetail/IntakeComponents/KeyValueRows';
import type { KeyValueEntry } from '@studio/components/IntakeDetail/IntakeComponents/keyValueTypes';
import { RawJsonDebug } from '@studio/components/IntakeDetail/IntakeComponents/RawJsonDebug';
import {
  buildSpanLlmEntries,
  buildSpanSummaryEntries,
} from '@studio/components/IntakeDetail/IntakeComponents/spanKeyValues';
import { SpanPayloadBlock } from '@studio/components/IntakeDetail/IntakeComponents/SpanPayloadBlock';
import { getSpanTemplate } from '@studio/components/IntakeDetail/SpanTemplates/registry';
import type { SpanSectionId } from '@studio/components/IntakeDetail/SpanTemplates/types';
import { type FC, type ReactNode, useEffect, useMemo, useRef, useState } from 'react';

// Entry ids that belong to the kind "Model & parameters" section, not Usage.
const LLM_PARAMETER_KEYS: ReadonlySet<string> = new Set(['model', 'provider', 'prompt_id']);

// Sections expanded by default unless a template overrides via `defaultOpen`.
const DEFAULT_OPEN: ReadonlySet<SpanSectionId> = new Set(['kind', 'llm', 'input', 'output']);

type GenericSectionId = Exclude<SpanSectionId, 'kind'>;

interface SpanSectionContext {
  span: Span;
  workspace: string;
  /** Span summary key/values for the Metadata section. */
  summaryEntries: readonly KeyValueEntry[];
  /** Token/cost key/values for the Usage section (model & params excluded). */
  usageEntries: readonly KeyValueEntry[];
  /** Bumped to focus the Annotations note field. */
  focusNoteNonce?: number;
}

// ── Generic section bodies (render the same way for every kind) ──────────────

const UsageSection: FC<SpanSectionContext> = ({ usageEntries }) => (
  <Stack className="min-w-0">
    <KeyValueGrid
      items={usageEntries.map((entry) => ({
        key: entry.id,
        label: entry.label,
        value: entry.value,
        wrapValue: entry.wrapValue,
      }))}
    />
  </Stack>
);

const InputSection: FC<SpanSectionContext> = ({ span }) => (
  <Stack className="min-w-0">
    <SpanPayloadBlock
      value={span.input}
      emptyMessage="No input payload was captured for this span."
    />
  </Stack>
);

const OutputSection: FC<SpanSectionContext> = ({ span }) => (
  <Stack className="min-w-0">
    <SpanPayloadBlock
      value={span.output}
      emptyMessage="No output payload was captured for this span."
    />
  </Stack>
);

const MetadataSection: FC<SpanSectionContext> = ({ summaryEntries }) => (
  <Stack className="min-w-0">
    <KeyValueRows entries={summaryEntries} />
  </Stack>
);

const AnnotationsSection: FC<SpanSectionContext> = ({ span, workspace, focusNoteNonce }) => (
  <Stack className="min-w-0">
    <AnnotationsPanel
      workspace={workspace}
      spanId={span.span_id}
      sessionId={span.session_id}
      focusNonce={focusNoteNonce}
    />
  </Stack>
);

/** The shared (non-kind) sections: a stable id → accordion value/label/body catalog. */
const SECTIONS: Record<
  GenericSectionId,
  { value: string; label: string; Body: FC<SpanSectionContext> }
> = {
  llm: { value: 'span-llm', label: 'Usage', Body: UsageSection },
  input: { value: 'span-input', label: 'Input', Body: InputSection },
  output: { value: 'span-output', label: 'Output', Body: OutputSection },
  metadata: { value: 'span-summary', label: 'Metadata', Body: MetadataSection },
  annotations: { value: 'span-annotations', label: 'Annotations', Body: AnnotationsSection },
};

const sectionLabel = (label: string): ReactNode => (
  <Text kind="body/semibold/sm" className="min-w-0">
    {label}
  </Text>
);

// The Annotations section trigger shows a count badge to the right of its label.
const annotationsSectionLabel = (label: string, count: number | undefined): ReactNode => (
  <Flex align="center" gap="density-sm" className="min-w-0">
    <Text kind="body/semibold/sm">{label}</Text>
    {count !== undefined && count > 0 && (
      <Badge color="gray" kind="solid">
        {count}
      </Badge>
    )}
  </Flex>
);

interface SpanMetadataAccordionsProps {
  span: Span;
  workspace: string;
  /**
   * Counters bumped by an external "expand all" / "collapse all" control (e.g.
   * the trace view's toolbar). Each increment opens/closes every section; the
   * sections are otherwise free to toggle individually.
   */
  expandToken?: number;
  collapseToken?: number;
  /** Annotation count for the span, shown on the Annotations section trigger. */
  annotationCount?: number;
  /** Bumped to open the Annotations section and focus its note field. */
  focusNoteNonce?: number;
}

export const SpanMetadataAccordions: FC<SpanMetadataAccordionsProps> = ({
  span,
  workspace,
  expandToken,
  collapseToken,
  annotationCount,
  focusNoteNonce,
}) => {
  const summaryEntries = useMemo(
    () => buildSpanSummaryEntries(span, { workspace }),
    [span, workspace]
  );
  // Usage shows only token/cost data; model & parameter keys live in the kind body.
  const usageEntries = useMemo(
    () => buildSpanLlmEntries(span).filter((entry) => !LLM_PARAMETER_KEYS.has(entry.id)),
    [span]
  );

  const template = useMemo(() => getSpanTemplate(span.kind), [span.kind]);

  // Kind-specific accordion sections (e.g. retriever query/documents). They sit
  // just below Annotations in the group and open by default. Built from the full
  // span, so they re-derive whenever the span changes.
  const customItems = useMemo<IntakeAccordionItem[]>(
    () => template.customSections?.(span) ?? [],
    [template, span]
  );
  const customValues = useMemo(() => customItems.map((item) => item.value), [customItems]);

  // Section layout is purely a function of the kind, so memoize it there: the
  // derived arrays keep stable identities across renders, which the re-seed and
  // token effects below depend on to avoid firing on every render.
  const { KindBody, accordionSectionIds, sectionAllValues, sectionDefaultOpenValues } =
    useMemo(() => {
      const templateIds = template.sections.filter((id): id is GenericSectionId => id !== 'kind');
      // Annotations lead the accordions (just below the kind "key details" body) so
      // reviewers can read and leave feedback before digging into payloads.
      const sectionIds = [
        ...templateIds.filter((id) => id === 'annotations'),
        ...templateIds.filter((id) => id !== 'annotations'),
      ];
      const openSet: ReadonlySet<SpanSectionId> = template.defaultOpen
        ? new Set(template.defaultOpen)
        : DEFAULT_OPEN;
      return {
        // The kind body renders above the accordion; the accordion shows the rest.
        KindBody: template.sections.includes('kind') ? template.Content : undefined,
        accordionSectionIds: sectionIds,
        sectionAllValues: sectionIds.map((id) => SECTIONS[id].value),
        sectionDefaultOpenValues: sectionIds
          .filter((id) => openSet.has(id))
          .map((id) => SECTIONS[id].value),
      };
    }, [template]);

  // Custom sections expand by default and join the full expand/collapse set.
  const allValues = useMemo(
    () => [...sectionAllValues, ...customValues],
    [sectionAllValues, customValues]
  );
  const defaultOpenValues = useMemo(
    () => [...sectionDefaultOpenValues, ...customValues],
    [sectionDefaultOpenValues, customValues]
  );

  const context: SpanSectionContext = {
    span,
    workspace,
    summaryEntries,
    usageEntries,
    focusNoteNonce,
  };
  const genericItems: IntakeAccordionItem[] = accordionSectionIds.map((id) => {
    const { value, label, Body } = SECTIONS[id];
    const slotLabel =
      id === 'annotations' ? annotationsSectionLabel(label, annotationCount) : sectionLabel(label);
    return { value, slotLabel, slotContent: <Body {...context} /> };
  });
  // Annotations leads, then the kind's custom sections, then the remaining
  // generic sections (e.g. Metadata).
  const leadingAnnotations = accordionSectionIds[0] === 'annotations' ? 1 : 0;
  const items: IntakeAccordionItem[] = [
    ...genericItems.slice(0, leadingAnnotations),
    ...customItems,
    ...genericItems.slice(leadingAnnotations),
  ];

  // Controlled so the toolbar's expand/collapse can drive every section at once
  // while individual rows stay independently toggleable. Re-seeds when the span
  // changes (a new span may expose a different set of sections).
  const [openSections, setOpenSections] = useState<string[]>(defaultOpenValues);
  useEffect(() => setOpenSections(defaultOpenValues), [span.span_id, defaultOpenValues]);

  // Bumping a token broadcasts "open/close everything"; guard on the previous
  // value so re-renders that don't change the token leave selections alone.
  const prevExpand = useRef(expandToken);
  const prevCollapse = useRef(collapseToken);
  useEffect(() => {
    if (expandToken !== prevExpand.current) {
      prevExpand.current = expandToken;
      setOpenSections(allValues);
    }
    if (collapseToken !== prevCollapse.current) {
      prevCollapse.current = collapseToken;
      setOpenSections([]);
    }
  }, [expandToken, collapseToken, allValues]);

  // "Add note" requests open the Annotations section (the panel then focuses its
  // note field). Init the ref to undefined so a mount that already carries a
  // nonce — e.g. a list row expanding from the button — still opens it.
  const annotationsValue = SECTIONS.annotations.value;
  const prevFocusNote = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (focusNoteNonce === undefined || focusNoteNonce === prevFocusNote.current) return;
    prevFocusNote.current = focusNoteNonce;
    if (allValues.includes(annotationsValue)) {
      setOpenSections((open) =>
        open.includes(annotationsValue) ? open : [...open, annotationsValue]
      );
    }
  }, [focusNoteNonce, allValues, annotationsValue]);

  return (
    <Stack gap="density-lg" className="min-w-0">
      {/* Pad via the wrapper (not banner margin) so the full-width banner stays
          inside the content and aligns with the top-level attributes. */}
      <div className="pl-density-2xl pr-density-lg min-w-0 empty:hidden">
        <SpanErrorBanner span={span} />
      </div>
      {KindBody ? (
        // Align the kind body with accordion section content below (sections
        // inset their body an extra step past the row padding).
        <Stack gap="density-md" className="pl-density-2xl pr-density-lg py-density-sm min-w-0">
          <KindBody span={span} workspace={workspace} />
        </Stack>
      ) : null}
      <IntakeAccordion
        variant="section"
        className="px-density-lg"
        value={openSections}
        onValueChange={setOpenSections}
        items={items}
      />
      <RawJsonDebug value={span} className="px-density-lg" />
    </Stack>
  );
};

const SpanErrorBanner: FC<{ span: Span }> = ({ span }) => {
  if (span.status !== SpanStatus.error) {
    return null;
  }
  return (
    <IntakeErrorBanner
      heading={span.error_type?.trim() || 'Error'}
      message={span.error_message?.trim() || 'No error message was captured for this span.'}
    />
  );
};
