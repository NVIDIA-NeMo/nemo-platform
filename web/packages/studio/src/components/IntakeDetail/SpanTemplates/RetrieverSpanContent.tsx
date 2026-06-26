// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Exports the kind body component alongside its accordion-section builder; the
// pair is small and co-located, so fast refresh's component-only rule is waived.
/* eslint-disable react-refresh/only-export-components */

import type { IntakeAccordionItem } from '@nemo/common/src/components/IntakeAccordion';
import type { Span } from '@nemo/sdk/generated/platform/schema';
import { Text } from '@nvidia/foundations-react-core';
import { SpanPayloadBlock } from '@studio/components/IntakeDetail/IntakeComponents/SpanPayloadBlock';
import {
  extractRetrievedDocuments,
  readRawAttribute,
} from '@studio/components/IntakeDetail/SpanTemplates/rawAttributes';
import {
  RankedDocumentList,
  TemplateKeyValues,
} from '@studio/components/IntakeDetail/SpanTemplates/templateFields';
import type { SpanTemplateContentProps } from '@studio/components/IntakeDetail/SpanTemplates/types';
import type { FC } from 'react';

const QUERY_SECTION = 'retrieval-query';
const DOCUMENTS_SECTION = 'retrieval-documents';

const sectionLabel = (label: string) => (
  <Text kind="body/semibold/sm" className="min-w-0">
    {label}
  </Text>
);

/**
 * RETRIEVER body: just the common status/timing values. The query and retrieved
 * documents are surfaced as their own accordion sections (see
 * `retrieverCustomSections`) so the Annotations section can lead the group.
 */
export const RetrieverSpanContent: FC<SpanTemplateContentProps> = ({ span }) => (
  <TemplateKeyValues span={span} fields={[]} />
);

/**
 * Retriever accordion sections. Elevates the retrieved documents that otherwise
 * sit in `raw_attributes` (`retrieval.documents.*`) into a ranked, scored list —
 * the data a reviewer actually cares about for a retrieval step — plus the query.
 */
export const retrieverCustomSections = (span: Span): IntakeAccordionItem[] => {
  const documents = extractRetrievedDocuments(span);
  const query = span.input?.trim();
  const topK = readRawAttribute(span, 'retrieval.top_k');
  const documentsLabel = documents.length
    ? `Documents (${documents.length}${typeof topK === 'number' ? ` of top_k=${topK}` : ''})`
    : 'Documents';

  return [
    {
      value: QUERY_SECTION,
      slotLabel: sectionLabel('Query'),
      slotContent: (
        <SpanPayloadBlock value={query} emptyMessage="No query was captured for this retrieval." />
      ),
    },
    {
      value: DOCUMENTS_SECTION,
      slotLabel: sectionLabel(documentsLabel),
      slotContent: (
        <RankedDocumentList
          documents={documents}
          emptyMessage="No retrieved documents were captured for this span."
        />
      ),
    },
  ];
};
