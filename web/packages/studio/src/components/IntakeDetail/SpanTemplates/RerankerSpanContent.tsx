// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { IntakeAccordion } from '@nemo/common/src/components/IntakeAccordion';
import { Stack, Text } from '@nvidia/foundations-react-core';
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
 * reranked document scores (`reranker.documents.*`) are a collapsible section,
 * open by default.
 */
export const RerankerSpanContent: FC<SpanTemplateContentProps> = ({ span }) => {
  const attributes = parseRawAttributes(span.raw_attributes);
  const documents = extractRerankedDocuments(span);
  const topN = asNumber(attributes['reranker.top_n']);
  const documentsLabel = documents.length
    ? `Ranked documents (${documents.length})`
    : 'Ranked documents';

  const fields: TemplateField[] = [
    { label: 'Model', value: span.model ?? undefined },
    { label: 'Top N', value: topN?.toLocaleString() },
  ];

  return (
    <Stack gap="density-xl" className="min-w-0">
      <TemplateKeyValues span={span} fields={fields} />
      <IntakeAccordion
        variant="section"
        defaultValue={[DOCUMENTS_SECTION]}
        items={[
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
        ]}
      />
    </Stack>
  );
};
