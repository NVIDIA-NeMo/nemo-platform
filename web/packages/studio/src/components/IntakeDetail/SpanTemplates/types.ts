// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { IntakeAccordionItem } from '@nemo/common/src/components/IntakeAccordion';
import type { Span } from '@nemo/sdk/generated/platform/schema';
import type { FC } from 'react';

export interface SpanTemplateContentProps {
  span: Span;
  workspace: string;
}

/**
 * The accordion sections a span detail view can show. `kind` is the
 * template-specific elevated section; the rest are generic, shared section
 * bodies (token usage/cost, request/response payloads, attribute bag, post-hoc
 * annotations).
 */
export type SpanSectionId = 'kind' | 'llm' | 'input' | 'output' | 'metadata' | 'annotations';

/** Color for a row-header badge; maps to the KUI `Badge` color. Defaults to gray. */
export type SpanHeaderBadgeColor = 'gray' | 'green' | 'red' | 'yellow' | 'blue';

export interface SpanHeaderBadge {
  text: string;
  color?: SpanHeaderBadgeColor;
}

/**
 * A per-kind view that elevates the data most relevant to one `SpanKind`
 * (e.g. retrieved documents for RETRIEVER) out of the generic span fields and
 * the `raw_attributes` bucket. Registered by kind in `registry.ts`.
 *
 * A template declares `sections`: the ordered set of accordion sections this
 * kind shows. Only sections that make sense for the kind are listed — a
 * retriever has no Output or token/cost section, so it omits them rather than
 * rendering empty ones. The kind-specific body comes from `Content`.
 */
export interface SpanTemplate {
  /**
   * The elevated, kind-specific body rendered above the accordion. Optional: a
   * template may omit it (and the `'kind'` section) to show only the shared
   * sections. The fallback template (e.g. UNKNOWN) still provides one —
   * `DefaultSpanContent` — to surface the common status/timing values that every
   * template shows at the top.
   */
  Content?: FC<SpanTemplateContentProps>;
  sections: readonly SpanSectionId[];
  /**
   * Sections expanded by default. When omitted, a sensible default applies
   * (kind/llm/input/output open; metadata/annotations collapsed).
   */
  defaultOpen?: readonly SpanSectionId[];
  /**
   * Raw-attribute namespaces this template surfaces in its own section or row
   * header (e.g. `['llm']`, `['retrieval']`). The Metadata section omits every
   * attribute under these prefixes, so anything already rendered isn't
   * duplicated there — keeping Metadata maintenance-free (it's whatever no
   * template has claimed).
   */
  attributeNamespaces?: readonly string[];
  /**
   * Kind-specific accordion sections rendered in the accordion group, after
   * Annotations (so reviewer feedback leads) and before the remaining generic
   * sections such as Metadata. Used by retriever/reranker to surface their query
   * and ranked-document sections. Returned items are open by default.
   */
  customSections?: (span: Span) => IntakeAccordionItem[];
  /**
   * Row-header overrides for the trace span list. `headerTitle` replaces the
   * span name (e.g. the evaluator name); `headerBadge` returns text shown as a
   * neutral badge in place of the trailing latency metric. Both read from the
   * span (including `raw_attributes`) and return undefined to fall back to the
   * default behavior.
   */
  headerTitle?: (span: Span) => string | undefined;
  headerBadge?: (span: Span) => SpanHeaderBadge | undefined;
}
