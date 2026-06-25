// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Exports the kind body component alongside its accordion-section builder; the
// pair is small and co-located, so fast refresh's component-only rule is waived.
/* eslint-disable react-refresh/only-export-components */

import type { IntakeAccordionItem } from '@nemo/common/src/components/IntakeAccordion';
import type { Span } from '@nemo/sdk/generated/platform/schema';
import { Text } from '@nvidia/foundations-react-core';
import {
  asNumber,
  extractRerankedDocuments,
  parseRawAttributes,
} from '@studio/components/IntakeDetail/SpanTemplates/rawAttributes';
import {
  RankedDocumentList,
  TemplateKeyValues,
  type TemplateField,
} from '@studio/components/IntakeDetail/SpanTemplates/templateFields';
import type { SpanTemplateContentProps } from '@studio/components/IntakeDetail/SpanTemplates/types';
import type { FC } from 'react';

const DOCUMENTS_SECTION = 'reranker-documents';

/**
 * RERANKER body. The rerank model/top-N float side by side as key values; the
 * reranked document scores are surfaced as their own accordion section (see
 * `rerankerCustomSections`) so the Annotations section can lead the group.
 */
export const RerankerSpanContent: FC<SpanTemplateContentProps> = ({ span }) => {
  const attributes = parseRawAttributes(span.raw_attributes);
  const topN = asNumber(attributes['reranker.top_n']);

  const fields: TemplateField[] = [
    { label: 'Model', value: span.model ?? undefined },
    { label: 'Top N', value: topN?.toLocaleString() },
  ];

  return <TemplateKeyValues span={span} fields={fields} />;
};

/** Reranker accordion sections: the reranked document scores (`reranker.documents.*`). */
export const rerankerCustomSections = (span: Span): IntakeAccordionItem[] => {
  const documents = extractRerankedDocuments(span);
  const documentsLabel = documents.length
    ? `Ranked documents (${documents.length})`
    : 'Ranked documents';

  return [
    {
      value: DOCUMENTS_SECTION,
      slotLabel: (
        <Text kind="body/semibold/sm" className="min-w-0">
          {documentsLabel}
        </Text>
      ),
      slotContent: (
        <RankedDocumentList
          documents={documents}
          emptyMessage="No reranked documents were captured for this span."
        />
      ),
    },
  ];
};
